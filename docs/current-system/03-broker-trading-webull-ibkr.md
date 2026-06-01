# 03 Broker 与交易逻辑

这部分是当前项目最容易混淆的地方。系统里同时存在 Webull、IBKR server connector、IBKR desktop sidecar 三套路径。它们共享部分接口和 UI，但连接方式、账户归属和下单方式不同。

## 1. Broker 三条路径

### 1.1 Webull server broker

Webull 是云 REST 接入：

```text
当前登录用户
  -> /broker/*
  -> broker_provider 发现该用户有 connected Webull credential
  -> build WebullBroker
  -> SdkWebullClient
  -> Webull OpenAPI REST
```

特点：

- per-user，每个用户可以绑定自己的 Webull credential。
- 不需要 TWS/IB Gateway。
- 不需要 Redis connector。
- 浏览器和 Electron 都能用。
- 连接状态来自 `broker_credentials`，不是 socket。
- 所有 `/broker/*` live call 都在服务端直接调 Webull SDK。

### 1.2 IBKR server broker

IBKR server 是平台共享 connector：

```text
FastAPI / worker
  -> build_broker(mode="server")
  -> RedisIBKRConnection
  -> Redis command queue
  -> run_broker.py 启动的 IBKRConnector
  -> LocalIBKRConnection
  -> TWS / IB Gateway
```

特点：

- server 进程和 worker 不直接开 TWS socket。
- 单独 connector 进程拥有唯一 `ib_async` socket。
- 账户通常是平台共享的单个 IBKR account。
- 需要 Redis。
- 状态和订单事件通过 DB mirror 展示。

### 1.3 IBKR desktop local broker

桌面本地路径：

```text
React renderer
  -> window.desktop.broker IPC
  -> Electron main process
  -> HTTP 127.0.0.1:<random_port> + Bearer token
  -> Python sidecar
  -> build_broker(mode="local")
  -> LocalIBKRConnection
  -> 用户本机 TWS / IB Gateway
```

特点：

- per desktop user，本地机器必须已经登录 TWS/IB Gateway。
- 不走 Redis connector。
- 不走 Webull。
- sidecar 只监听 loopback。
- token 只存在 Electron main process，renderer 拿不到。
- 服务端仍负责登录、分析、审批、订单 mirror 和业绩统计。

## 2. Active broker 如何选择

服务端在 `tradingagents/api/broker_provider.py` 做选择：

```text
resolve_active_broker(session, user, config):
  如果该 user 有 broker=webull 且 status=connected 的 credential
      -> webull
  否则
      -> config["broker"]，默认来自 TRADINGBOT_BROKER
```

`/broker/status`、`/broker/account`、`/broker/positions`、交易建议、手动服务端下单都走这个选择。

因此：

- 一个用户绑定 Webull 后，该用户的 server broker 会优先 Webull。
- 没有绑定 Webull 的用户继续走 IBKR server connector。
- 桌面端如果本地 IBKR 已连接，但 server status 是可用 Webull，交易建议和手动快单会优先用 Webull server path，避免误落到本地 IBKR。

## 3. Webull 凭据设计

表：`broker_credentials`。唯一键是 `(user_id, broker)`。

关键字段：

- `user_id`
- `broker`：当前只用 `webull`
- `account_id`
- `region`
- `auth_type`：`oauth` 或 `api_key`
- `access_token_enc`
- `refresh_token_enc`
- `app_key_enc`
- `app_secret_enc`
- `token_expires_at`
- `refresh_expires_at`
- `scope`
- `status`：`connected/expired/revoked`

### 3.1 OAuth 模式

流程：

1. 用户登录 Web。
2. 前端请求 `GET /broker/oauth/webull/authorize`。
3. 后端生成 Fernet 加密 state，内容含 user_id 和 timestamp，TTL 10 分钟。
4. 前端跳转 Webull 授权页。
5. Webull callback 到 `/broker/oauth/webull/callback?code&state`。
6. 后端解 state 得到 user_id。
7. 用 code 换 access/refresh token。
8. token 加密保存到该 user 的 `broker_credentials`。
9. 重定向回 `/broker?connected=webull` 或带 error。

OAuth token 过期处理：

- `build_user_broker()` 构造 broker 前检查 token 是否快过期。
- 快过期且有 refresh token 时自动 refresh，并回写 DB。
- 无法 refresh 时 credential 标记 expired，接口返回需要重新连接。

### 3.2 API key 模式

用户在 Webull 连接卡输入：

- `app_key`
- `app_secret`
- 可选 `account_id`

后端 `POST /broker/oauth/webull/api-key`：

1. trim app_key/app_secret。
2. 用 `SdkWebullClient(auth_type=api_key)` 校验 health。
3. 从 health accounts 选账户：
   - 请求里传了 account_id：必须在 Webull 返回 accounts 里，除非 accounts 为空。
   - 只返回一个账户：自动选择。
   - 多个账户且没传 account_id：409，要求用户填写。
   - 没有账户：409。
4. app_key/app_secret 加密保存。
5. credential status=connected。

API key 模式没有 refresh token，`ensure_fresh_token()` 不会刷新。

当前设计里同一个用户只能有一个 Webull credential。如果要让一个用户同时管理多个 Webull 账户，需要至少改：

- `broker_credentials` 唯一约束。
- Webull status 和 active account 选择。
- 前端连接/切换账户 UI。
- `/broker/*` 请求如何指定 account。

## 4. WebullBroker 做什么

`tradingbot/broker/webull.py` 是 broker adapter。它不直接依赖 SDK，而是依赖 `WebullClient` protocol。

它负责把 Webull SDK 返回的 dict 归一化成统一模型：

- `AccountInfo`
- `Position`
- `Order`
- preview dict

关键逻辑：

- Webull 下单需要 `instrument_id`，不是 ticker。adapter 会调用 `resolve_instrument(symbol)` 并缓存。
- 下单 payload 包含：
  - `client_order_id`
  - `instrument_id`
  - `symbol`
  - `instrument_type=EQUITY`
  - `side=BUY/SELL`
  - `order_type`
  - `qty/quantity`
  - `entrust_type=QTY`
  - `combo_type=NORMAL`
  - `support_trading_session=CORE`
  - `market=<REGION>`
  - `extended_hours_trading=False`
- limit order 必须有 `limit_price`。
- 下单失败不自动重试，避免重复单。
- `get_latest_price()` 优先读 `price -> last -> close -> ask -> bid`。
- preview 输出会归一化为接近 IBKR whatIf 的字段：
  - `init_margin`
  - `maint_margin`
  - `commission`
  - `equity_with_loan`
  - `estimated_cost`
  - `buying_power`
  - `warning`

## 5. IBKR server connector

IBKR server connector 解决的问题是：IBKR TWS API socket 不适合让多个 web/worker 进程各自连接并竞争。

路径：

1. `run_broker.py` 启动 connector。
2. connector 构造 `LocalIBKRConnection`。
3. connector 消费 Redis command queue。
4. FastAPI 构造 `RedisIBKRConnection`。
5. FastAPI 调 `get_account/get_positions/preview_order/submit_order/cancel_order` 时，实际把命令放入 Redis。
6. connector 执行后把 response 放到 per-command reply queue。

`IBKRBroker` 只做业务映射，不 import `ib_async`，也不直接开 socket。真正 socket 在 `LocalIBKRConnection`。

注意：

- IBKR 整股限制：qty 必须是整数且 >= 1。
- limit order 必须有价格。
- preview 是 IBKR `whatIf` 风格。
- 下单不重试。
- fills 是异步的，服务端提交后先 mirror 为 submitted，之后依赖 connector/order event 更新。

## 6. Desktop sidecar

Electron 桌面端启动后，main process 会后台启动 Python sidecar。

安全设计：

- sidecar 只绑定 `127.0.0.1`。
- main process 随机生成 token。
- 每个 sidecar 请求都要 `Authorization: Bearer <token>`。
- renderer 只能通过 preload 暴露的 IPC API 调 main process。
- renderer 不知道 token 和 sidecar port。

sidecar endpoint：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/ping` | readiness，不需要 token |
| `GET` | `/health` | 本地 broker 状态 |
| `POST` | `/discover` | 扫描 IBKR 常见端口 |
| `POST` | `/connect` | 连接 TWS/IB Gateway |
| `POST` | `/disconnect` | 断开 |
| `GET` | `/account` | 本地账户 |
| `GET` | `/positions` | 本地持仓 |
| `GET` | `/orders` | 本地订单 |
| `POST` | `/quote` | 本地报价 |
| `POST` | `/preview` | 本地订单预览 |
| `POST` | `/execute` | 本地下单 |
| `POST` | `/orders/{id}/cancel` | 本地取消订单 |

sidecar 内部有单独 worker thread。原因是 `ib_async` 需要在拥有事件循环的单线程里运行，所有 broker call 都串行投递到这个线程。

## 7. 交易建议生成

前端入口在分析详情页：

- run 必须 `succeeded`。
- 当前用户必须 `admin/operator`。
- result.decision 必须是可交易信号：
  - `BUY`
  - `OVERWEIGHT`
  - `UNDERWEIGHT`
  - `SELL`
- `HOLD` 显示无动作，不调用 API。
- 必须有可用 broker account；没有则提示跳转 `/broker` 绑定/连接账户。

server proposal：

```text
POST /broker/approvals { run_id }
  -> 校验 run succeeded
  -> 读取 AnalysisRunResult
  -> 取 result.decision 和 final_trade_decision reasoning
  -> TradeProposalBuilder.build()
```

desktop local proposal：

```text
front tradeFlow.createProposal()
  -> 如果 server 是 Webull，可直接 POST /broker/approvals
  -> 否则 Electron local channel 取 account/positions/quote
  -> POST /broker/local/proposals
  -> 服务端用 SnapshotBroker 做 sizing/risk
```

## 8. SignalMapper 数量计算

`SignalMapper` 把五档评级转成交易指令：

| 信号 | 动作 | 默认比例 |
| --- | --- | --- |
| `BUY` | 买入 | 用现金 5% |
| `OVERWEIGHT` | 买入 | 用现金 3% |
| `HOLD` | 不交易 | 0 |
| `UNDERWEIGHT` | 卖出 | 卖已有持仓 50% |
| `SELL` | 卖出 | 清仓 |

买入数量：

```text
qty = available_cash * allocation_fraction / price
```

当前 proposal builder 的边界处理：

- 买入算出 `0 < qty < 1` 且现金够买 1 股时，会提升到 1 股。
- 如果现金连 1 股都不够，返回 `insufficient cash for 1 share`。
- 卖出时没有持仓或卖出后整数股 < 1，会返回 `computed quantity < 1 share`。
- 最终会 `int(qty)`，所以目前交易建议按整股处理。

常见提示含义：

- `Hold — no action taken`：最终评级是 HOLD 或未知信号被当作 HOLD。
- `price unavailable: ...`：当前 broker 报价拿不到，可能是连接、权限、ticker、行情权限或 Webull/IBKR 响应问题。
- `computed quantity < 1 share`：按配置仓位、现金、价格、持仓计算后不足 1 股；卖出场景常见于没有持仓。

## 9. RiskGate

RiskGate 是程序化硬风控，LLM 不能绕过。

检查顺序：

1. 市场是否开盘。paper trading 默认不强制开盘。
2. 日内亏损熔断。
3. 买入后现金不能低于 `MIN_CASH_RESERVE`。
4. 总敞口不能超过 `MAX_TOTAL_EXPOSURE_PCT`。
5. 单票不能超过 `MAX_SINGLE_POSITION_PCT`。
6. 已在单票 cap 附近时不能继续买到超限。
7. 卖出不能超过实际持仓。

风控可能：

- 直接拒绝。
- 返回 `adjusted_qty`，把数量压低。
- 通过。

交易建议生成时跑第一道 RiskGate；真正批准执行时再跑第二道 RiskGate。

## 10. 人工审批和执行

approval 状态机：

```text
pending
  -> approved
     -> submitted
     -> failed

pending
  -> rejected
  -> expired
```

批准接口：

```text
POST /broker/approvals/{approval_id}/approve
```

执行服务逻辑：

1. 读取 approval，必须是 `approved`。
2. 重新获取 live price。
3. 重新跑 RiskGate。
4. best-effort preview：
   - 成功则写 `whatif_init_margin` 和 `whatif_commission`。
   - 失败只记录 warning，不阻塞下单。
5. submit order，绝不自动重试。
6. upsert `broker_orders` mirror。
7. approval 标记 `submitted`。
8. 如果下单失败，approval 标记 `failed`。

桌面本地执行不同：

1. 服务端生成 approval。
2. 前端批准时先让 sidecar 本地下单。
3. 下单返回后调用 `/broker/approvals/{id}/executed`。
4. 服务端把 approval approve/submit，并写 `broker_orders` mirror。

## 11. 手动快速下单

手动下单不是从分析 run 来，不创建 approval。

前端 `manualTradeRoute()`：

1. 如果 server status 是可用 Webull，route=`server`。
2. 否则如果是 Electron 且 local IBKR 可执行，route=`local`。
3. 否则 route=null。

server route：

```text
QuickTrade
  -> POST /broker/orders/preview
  -> POST /broker/orders
  -> 服务端 broker 真实下单
  -> upsert broker_orders
```

local route：

```text
QuickTrade
  -> sidecar /preview
  -> sidecar /execute
  -> POST /broker/orders/manual
  -> 服务端只 mirror，不再真实下单
```

## 12. 订单和业绩数据的边界

`GET /broker/orders` 读的是服务端 `broker_orders` mirror，不一定是 broker 原始订单全量列表。

mirror 来源：

- 服务端 `/broker/orders` 下单后写入。
- approval 执行后写入。
- desktop local approval 执行后回报写入。
- desktop manual order 回报写入。
- IBKR connector 订单事件可能更新。

Webull 当前没有类似 IBKR connector 的实时 order event mirror，所以 Webull 订单主要靠服务端下单路径写入。

业绩统计：

- trades 来自 filled orders。
- equity curve / drawdown / Sharpe 来自 portfolio snapshots。
- snapshots 由前端或桌面定期推送 `/broker/snapshot`。

## 13. Webull 和 app_key/app_secret 的账户关系

现在的实现支持“用户提交自己的 Webull app_key/app_secret 并使用”。这可以实现多用户各自使用自己的 Webull Trading API 凭证，因为 credential 存储按 `user_id` scoped。

但要区分两个层级：

- 多用户各自绑定自己的 app_key/app_secret：当前架构支持。
- 同一个用户绑定多个 Webull account/app_key：当前表约束不支持，需要改造。

从 Webull API key 模式看，如果一个 app_key/app_secret 只能访问某一个账户，那它会自然绑定到该 `account_id`。如果一个凭据能列出多个账户，当前接口要求用户指定其中一个账户。

## 14. Webull preview 500 的定位方向

`POST /broker/orders/preview` 对参数错误返回 422，对 broker/SDK 异常返回 502。前端看到 500/502 类错误时，通常不在 UI 路由层，而在：

- Webull SDK preview 返回 shape 和 adapter 归一化不一致。
- payload 缺 Webull 必填字段。
- `instrument_id` 解析失败。
- account_id 不正确。
- app_key/app_secret 或 endpoint/region/paper 环境不匹配。
- Webull SDK 自己抛出未被转换的异常。

当前 adapter 已在 payload 中包含 `market`、`combo_type`、`support_trading_session=CORE` 等 Webull 必填字段。继续排查时优先看服务端日志里 Webull SDK 的原始异常。
