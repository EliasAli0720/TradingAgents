# IBKR 接入设计

日期：2026-05-29

## 背景

当前系统已有两条相关能力：

- 分析服务：FastAPI 后端位于 `tradingagents/api/`，React 前端位于 `web/src/`，前端统一通过 `/api` 调后端。
- 交易执行：`tradingbot/broker/base.py` 定义 `BrokerAdapter`，现有 `MockBroker` 和 `AlpacaBroker` 已经把账户、持仓、行情、下单封装成统一接口。`AutoTrader` 通过 `BrokerAdapter`、`RiskGate`、`PortfolioManager` 完成分析信号到交易执行的链路。

IBKR 接入的目标不是新增一套独立交易系统，而是把 IBKR 作为新的 broker backend 接入现有系统，让分析、风控、审批、下单、持仓展示仍走统一后端。

## 目标

- 接入 IBKR Web API，让系统可以查询 IBKR 账户、持仓、行情和订单。
- 支持服务端部署：用户只访问前端，不直接访问 IBKR Gateway 或 IBKR API。
- 复用现有 `BrokerAdapter`、`RiskGate`、`PortfolioManager`、FastAPI 鉴权和 React 前端结构。
- 第一阶段支持平台级或管理员级 IBKR 账户交易，优先跑通 paper trading。
- 为后续“每个用户绑定自己的 IBKR 账户”预留 OAuth 账户连接模型，但不在第一阶段实现。
- 所有真实下单默认需要人工审批，避免 agent 直接自动交易真实资金。

## 非目标

- 第一阶段不实现多 IBKR 用户 OAuth 授权。
- 第一阶段不实现期权、期货、组合保证金、bracket order、复杂条件单。
- 第一阶段不实现 WebSocket 实时行情；用 REST snapshot 满足最小交易链路。
- 第一阶段不让前端直连 `https://localhost:5000/v1/api`。
- 第一阶段不实现完全无人值守 IBKR 登录，因为个人 Client Portal Gateway 登录本身不适合这样设计。

## 官方约束摘要

来源：

- IBKR Client Portal API v1 文档：`https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/`
- IBKR Web API 文档入口：`https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/`

约束：

- 个人账户使用 Client Portal API 时，通常需要运行本地 Client Portal Gateway，基础地址是 `https://localhost:5000/v1/api`。
- Gateway 登录通常需要浏览器交互和 2FA，不适合做成云端完全自动登录。
- `/iserver` 相关交易、行情和订单接口依赖 brokerage session。
- Gateway 会话需要保活，官方建议定期调用 `/tickle`。
- 行情 snapshot 首次请求可能只是预热，需要再次请求才返回完整字段。
- IBKR 有全局和 endpoint 级限速，设计中必须加客户端限流和失败重试策略。
- 下单接口可能返回 warning/reply，需要调用 `/iserver/reply/{replyId}` 确认后订单才真正继续。
- Web API / OAuth 是更适合第三方平台和多用户授权的方向，但 OAuth 接入涉及应用审批、token 存储、授权范围和合规流程。

## 架构方案比较

### 方案 A：服务端部署 Client Portal Gateway，平台级 IBKR 账户

```
React SPA
  -> FastAPI /api
    -> BrokerService
      -> IBKRBroker
        -> IBKR Client Portal Gateway
          -> IBKR
```

特点：

- 最容易接入当前系统。
- 不要求每个用户本地运行 Gateway。
- Gateway 与后端运行在同一台服务器或同一内网。
- 前端只看到系统 API，不知道 IBKR Gateway 地址。
- 需要管理员维护 Gateway 登录状态。
- 适合自用、团队内部、单账户 paper/live trading。

风险：

- 如果服务端在云上，IBKR 登录和 2FA 体验需要额外运维流程。
- 多用户自带 IBKR 账户的场景不适合用这个方案硬撑。

### 方案 B：每个用户本地运行 Gateway，浏览器连接本机

```
用户浏览器
  -> 用户本机 Gateway
  -> IBKR
```

特点：

- 用户各自登录自己的 IBKR。
- 不需要平台托管用户交易凭证。

风险：

- 和当前“服务端运行，用户只访问前端”的部署模式冲突。
- 浏览器跨域、证书、内网访问、用户本机安装 Gateway 都会带来很高支持成本。
- 后端难以统一做风控、审计和订单记录。

结论：不采用。

### 方案 C：IBKR OAuth，多用户授权

```
React SPA
  -> FastAPI /api
    -> BrokerAccountService
      -> IBKR OAuth token
      -> IBKR Web API
```

特点：

- 最适合 SaaS 化和“每个用户自己的 IBKR 账户”。
- 用户在 IBKR 授权，后端保存加密 token。
- 可以和现有用户系统、角色权限、审计、审批流结合。

风险：

- 接入周期更长。
- 需要申请和配置 IBKR 应用。
- 需要 token 生命周期、安全存储、scope、回调、撤销授权处理。
- 交易合规和责任边界更复杂。

结论：作为第二阶段演进方向，不阻塞第一阶段。

## 推荐方案

第一阶段采用“方案 A：服务端 Gateway + 平台级 IBKR 账户”，同时在数据模型和服务边界上预留“方案 C：用户级 OAuth”。

推荐原因：

- 当前代码已经有 broker 抽象，新增 `IBKRBroker` 就能接入 `AutoTrader`。
- 当前前端已经统一调用 FastAPI，新增 broker 页面和审批页面即可。
- 第一阶段能以 paper trading 快速验证完整链路。
- 将来做 OAuth 时，可以把 `IBKRBroker` 的 transport/session 部分替换为 OAuth 凭证提供器，保留上层 `BrokerAdapter` 和交易审批模型。

## 系统边界

### 前端边界

前端只负责：

- 展示 IBKR 连接状态。
- 展示账户、持仓、订单、待审批交易。
- 发起“预览订单”“批准订单”“取消订单”等业务动作。
- 展示 Gateway 需要重新登录的状态提示。

前端不负责：

- 存储 IBKR 密钥或 token。
- 直接调用 IBKR Gateway。
- 绕过后端风控下单。

### 后端边界

后端负责：

- 维护 IBKR Gateway 连接和 session 状态。
- 统一封装 IBKR REST API。
- 统一处理 IBKR 错误、限流、reply 确认、行情字段映射。
- 调用现有风控和订单记录。
- 提供给前端的稳定业务 API。
- 记录审计日志：谁在什么时候批准了什么订单，提交结果是什么。

### Gateway 边界

Gateway 只作为 IBKR 官方本地代理：

- 不暴露给公网。
- 只允许后端所在主机或内网访问。
- 登录状态由管理员维护。
- 通过后端健康检查展示给前端。

## 第一阶段功能范围

### 连接状态

系统提供 IBKR 连接状态：

- `gateway_online`：Gateway HTTP 是否可访问。
- `authenticated`：IBKR session 是否认证。
- `brokerage_session`：`/iserver` 交易 session 是否可用。
- `account_id`：当前选择账户。
- `paper`：当前是否 paper 环境。
- `last_tickle_at`：最近一次保活时间。
- `last_error`：最近一次连接错误摘要。

状态异常时：

- 禁止提交新订单。
- 允许查看系统内历史分析和本地数据库记录。
- 前端显示“需要管理员重新登录 IBKR”。

### 账户和持仓

后端通过 IBKR 获取：

- 账户列表。
- 当前账户 summary。
- cash、net liquidation、buying power、equity。
- 当前持仓，映射为现有 `Position`。

由于 IBKR 字段和 Alpaca 字段不完全一致，第一阶段按系统已有模型做最小映射：

- `AccountInfo.cash`：优先使用 settled cash / available funds，字段不存在时用 cash balance。
- `AccountInfo.portfolio_value`：使用 net liquidation。
- `AccountInfo.buying_power`：使用 buying power 或 available funds。
- `AccountInfo.equity`：使用 net liquidation。
- `Position.avg_entry_price`：使用 average cost。
- `Position.current_price`：优先用 market price，缺失时用 snapshot last price。
- `Position.unrealized_pnl`：使用 IBKR 返回值，缺失时本地计算。

### 行情

第一阶段只实现 `get_latest_price(ticker)`：

流程：

1. 通过 `/iserver/secdef/search` 把 ticker 解析为 `conid`。
2. 缓存 `ticker -> conid`。
3. 通过 `/iserver/marketdata/snapshot` 获取 last/bid/ask。
4. 如果 last 不可用，用 `(bid + ask) / 2`。
5. 如果 snapshot 首次返回为空，短暂等待后重试一次。

限制：

- 仅支持美股股票。
- 不在第一阶段承诺 tick 级实时性。
- 不把 IBKR 行情作为 TradingAgents 的历史分析数据源，分析数据仍走现有 dataflows。

### 下单

第一阶段支持：

- BUY / SELL。
- MARKET / LIMIT。
- `DAY` 和 `GTC`。
- 股票整数股。
- 下单前 what-if / preview。
- 下单后查询订单状态。
- 取消 open order。

不支持：

- fractional shares。
- option spread。
- bracket order。
- stop / stop-limit。
- short sell 特殊风控。
- 多账户批量下单。

下单流程：

```
analysis run succeeded
  -> 生成交易建议
  -> SignalMapper 转成 OrderInstruction
  -> RiskGate 计算和校验数量
  -> 写入 trade_approvals(status=pending)
  -> 前端展示待审批订单
  -> operator/admin 点击批准
  -> 后端重新读取价格和账户
  -> RiskGate 二次校验
  -> IBKR what-if preview
  -> IBKR place order
  -> 如 IBKR 返回 reply id，按策略处理
  -> 写入 trade_orders / PortfolioManager
  -> 前端显示结果
```

### IBKR reply 处理策略

IBKR 下单可能返回 warning 或确认请求。第一阶段采用保守策略：

- 默认不自动确认所有 warning。
- 后端把 reply 内容写入订单审批结果，状态为 `requires_confirmation`。
- 前端展示 IBKR warning 文本。
- 用户再次点击“确认提交”后，后端调用 `/iserver/reply/{replyId}`。

可配置白名单：

- 后续可增加 `IBKR_AUTO_CONFIRM_REPLY_CODES`，只自动确认明确安全的常见提示。
- 第一阶段不启用自动确认白名单。

## 后端设计

### 新增 broker adapter

文件：

- `tradingbot/broker/ibkr.py`

职责：

- 实现 `BrokerAdapter`。
- 把系统统一模型映射到 IBKR API。
- 不直接依赖 FastAPI。
- 可被 CLI、scheduler、worker、API 共用。

核心类：

```python
class IBKRBroker(BrokerAdapter):
    def __init__(
        self,
        base_url: str,
        account_id: str | None = None,
        verify_ssl: bool = False,
        timeout_seconds: float = 10.0,
    ):
        self.base_url = base_url
        self.account_id = account_id
        self.verify_ssl = verify_ssl
        self.timeout_seconds = timeout_seconds
```

关键方法：

- `health()`：返回 Gateway 和 auth 状态。
- `ensure_brokerage_session()`：需要交易/行情前调用。
- `tickle()`：保活。
- `get_account()`。
- `get_positions()`。
- `get_position(ticker)`。
- `get_latest_price(ticker)`。
- `submit_order(ticker, qty, side, order_type, limit_price, time_in_force)`。
- `get_order(order_id)`。
- `cancel_order(order_id)`。
- `get_order_history(limit)`。

### IBKR API client

文件：

- `tradingbot/broker/ibkr_client.py`

职责：

- 封装 HTTP。
- 做 base URL 拼接。
- 做 request timeout。
- 做错误类型转换。
- 做简单限流。
- 处理 Gateway 自签证书。

错误类型：

- `IBKRGatewayUnavailable`
- `IBKRAuthenticationRequired`
- `IBKRBrokerageSessionRequired`
- `IBKRRateLimited`
- `IBKROrderRequiresConfirmation`
- `IBKROrderRejected`
- `IBKRUnexpectedResponse`

限流：

- 第一阶段使用进程内 token bucket。
- 默认全局 `8 req/s`，低于官方全局限制，留出余量。
- 429 时按响应信息或指数退避重试只读请求。
- 下单请求不自动重试，避免重复订单。

### session monitor

文件：

- `tradingbot/broker/ibkr_session.py`

职责：

- 后台维护 IBKR 状态。
- 每 60 秒调用 `/tickle`。
- 定期调用 auth status。
- 状态变化时写日志。
- 可被 FastAPI startup 初始化，也可被 scheduler 初始化。

状态机：

```
unconfigured
  -> gateway_offline
  -> gateway_online
  -> authenticated
  -> brokerage_ready
  -> degraded
```

状态说明：

- `unconfigured`：未配置 `IBKR_BASE_URL` 或未启用 ibkr。
- `gateway_offline`：Gateway 不可访问。
- `gateway_online`：Gateway 可访问但未登录。
- `authenticated`：已登录但 brokerage session 未就绪。
- `brokerage_ready`：可以查询 `/iserver` 和提交订单。
- `degraded`：近期请求失败或限流严重，禁止新下单。

### broker factory

当前 `run_bot.py` 和 `tradingbot/dashboard/app.py` 各自构造 broker。第一阶段先保持小改动：

- 新增 `tradingbot/broker/factory.py`，集中 `build_broker(config)`。
- `run_bot.py`、dashboard、API broker router 共用 factory。
- 支持 `mock`、`alpaca`、`ibkr`。

配置：

```env
TRADINGBOT_BROKER=ibkr
IBKR_BASE_URL=https://localhost:5000/v1/api
IBKR_ACCOUNT_ID=U1234567
IBKR_VERIFY_SSL=false
IBKR_AUTO_TICKLE=true
IBKR_ORDER_CONFIRMATION_MODE=manual
IBKR_PAPER=true
```

`IBKR_VERIFY_SSL=false` 是因为本地 Gateway 常见自签证书。只允许在 Gateway 不暴露公网时使用。

### FastAPI broker router

文件：

- `tradingagents/api/routers/broker.py`

路由：

- `GET /broker/status`
- `GET /broker/accounts`
- `GET /broker/account`
- `GET /broker/positions`
- `GET /broker/orders`
- `GET /broker/orders/{order_id}`
- `POST /broker/orders/preview`
- `POST /broker/orders`
- `POST /broker/orders/{order_id}/cancel`
- `GET /broker/approvals`
- `POST /broker/approvals/{approval_id}/approve`
- `POST /broker/approvals/{approval_id}/reject`
- `POST /broker/approvals/{approval_id}/confirm-reply`

权限：

- 只读账户、持仓、订单：`admin`、`operator`。
- 订单 preview、拒绝审批：`admin`、`operator`。
- 最终下单、批准审批、确认 IBKR reply、取消外部订单：默认只允许 `admin`。如果后续需要给交易员放权，再把 `operator` 加入这些接口的角色列表。
- 普通用户第一阶段不能交易。

CSRF：

- 所有 `POST` 路由沿用现有 CSRF 中间件。

### 数据模型

新增表建议：

#### `broker_connections`

保存 broker 配置状态，不保存 Gateway 密码。

字段：

- `connection_id`
- `broker`：`ibkr`
- `mode`：`gateway` 或 `oauth`
- `account_id`
- `display_name`
- `paper`
- `status`
- `last_checked_at`
- `last_error`
- `created_at`
- `updated_at`

第一阶段可只保存一条平台级连接。

#### `trade_approvals`

保存 agent 生成但尚未提交的交易建议。

字段：

- `approval_id`
- `run_id`
- `user_id`
- `broker`
- `account_id`
- `ticker`
- `conid`
- `side`
- `order_type`
- `quantity`
- `limit_price`
- `time_in_force`
- `estimated_price`
- `estimated_value`
- `risk_verdict`
- `agent_reasoning`
- `status`：`pending`、`approved`、`rejected`、`submitted`、`requires_confirmation`、`failed`、`expired`
- `ibkr_reply_id`
- `ibkr_reply_message`
- `approved_by`
- `approved_at`
- `submitted_order_id`
- `created_at`
- `updated_at`

#### `broker_orders`

保存外部 broker 订单镜像。

字段：

- `broker_order_id`
- `broker`
- `account_id`
- `approval_id`
- `ticker`
- `conid`
- `side`
- `order_type`
- `quantity`
- `limit_price`
- `time_in_force`
- `status`
- `filled_qty`
- `filled_avg_price`
- `submitted_at`
- `updated_at`
- `raw_response`

### 审计

第一阶段可以把审批和订单状态直接落在 `trade_approvals`、`broker_orders`。后续如需要更强审计，新增 append-only `broker_audit_events`：

- `event_id`
- `actor_user_id`
- `event_type`
- `entity_type`
- `entity_id`
- `payload`
- `created_at`

## 前端设计

新增页面：

- `/broker`
- `/broker/orders`
- `/broker/approvals`

导航：

- 侧边栏新增“交易连接”或“Broker”。
- 仅 `admin`、`operator` 可见。

### Broker 状态页

展示：

- 当前 broker：Mock / Alpaca / IBKR。
- Gateway 状态。
- IBKR 认证状态。
- Brokerage session 状态。
- 当前账户。
- Paper/live 标识。
- 最近错误。
- 最近保活时间。

操作：

- 刷新状态。
- 初始化 brokerage session。
- 只显示“去服务器登录 Gateway”的说明，不在前端嵌入 IBKR 登录页。

### 持仓页

复用现有占位页面 `/portfolio`，改为调用 `/broker/positions`。

展示：

- ticker
- quantity
- avg cost
- current price
- market value
- unrealized P&L
- unrealized P&L %

### 审批页

展示 pending approvals：

- ticker
- side
- quantity
- estimated price/value
- signal
- risk verdict
- agent reasoning 摘要
- 创建时间

操作：

- Approve
- Reject
- Preview
- Confirm IBKR Reply

交互约束：

- Approve 前必须展示最新价格和二次风控结果。
- 如果 IBKR 返回 reply，页面进入二次确认态。
- 二次确认按钮文案必须明确显示 IBKR warning。

## 与 AutoTrader 的结合

当前 CLI 版本 `AutoTrader` 在 `require_approval=True` 时通过命令行 `input()` 审批。服务端版本不能使用阻塞输入，需要新增非阻塞审批模式。

建议拆分：

- `AutoTrader.run_single()` 继续负责分析、映射和风控。
- 新增 `TradeApprovalService` 负责把交易建议持久化为 `trade_approvals`。
- 新增 `TradeExecutionService` 负责审批后的二次风控、what-if、真实下单和记录。

流程：

```
AnalysisRun succeeded
  -> TradeProposalBuilder 从 result.decision/final_state 生成 proposal
  -> SignalMapper 映射 BUY/SELL/HOLD
  -> RiskGate 初审
  -> TradeApprovalService.create_pending()
  -> 前端审批
  -> TradeExecutionService.execute_approved()
  -> IBKRBroker.submit_order()
  -> PortfolioManager.record_trade()
```

第一阶段可以只让手动触发的交易建议进入审批表，不自动把所有分析 run 都变成交易建议。这样降低误交易风险。

## 安全设计

### 网络

- Gateway 只监听本机或私有网络。
- 不把 Gateway 端口暴露到公网。
- 生产环境通过防火墙限制只有后端进程可访问 Gateway。
- 如果后端和 Gateway 不在同一台机器，必须走私有网络或 SSH tunnel，不通过公网明文访问。

### 认证和权限

- 前端沿用当前 session cookie + CSRF。
- broker API 全部需要登录。
- 下单相关 API 仅 `admin`、`operator`。
- 后续多用户 OAuth 时，普通用户只能管理自己的 broker connection，不能访问其他用户账户。

### 秘密和 token

第一阶段 Gateway 不在系统中保存 IBKR 密码。

第二阶段 OAuth token：

- 复用 `tradingagents/api/crypto.py` 的 Fernet 加密能力。
- token 只保存密文。
- refresh token 和 access token 分开记录。
- 所有 token 解密只发生在后端请求 IBKR 前。

### 真实交易保护

- `IBKR_PAPER=true` 作为默认。
- live 模式启动时要求显式 `IBKR_PAPER=false`。
- live 模式默认强制人工审批。
- live 模式禁止自动确认 IBKR reply。
- 下单前二次读取账户和价格，避免审批后市场变化导致超额下单。
- 所有订单写入本地数据库，便于追踪。

## 错误处理

### Gateway 离线

- `GET /broker/status` 返回 `gateway_offline`。
- 下单返回 `409 broker unavailable`。
- 前端显示“Gateway 未连接，需要管理员检查服务”。

### 未登录或 session 过期

- 状态返回 `gateway_online` 或 `authenticated=false`。
- 禁止下单。
- 前端显示“IBKR 需要重新登录”。

### Brokerage session 未就绪

- 后端尝试 `ssodh/init`。
- 如果仍失败，状态返回 `authenticated` 但 `brokerage_session=false`。
- 禁止交易接口。

### IBKR 限流

- 只读请求可短暂退避重试。
- 下单请求不自动重试。
- 前端显示“IBKR 限流，请稍后重试”。

### 下单需要确认

- 后端不直接确认。
- `trade_approvals.status = requires_confirmation`。
- 保存 `ibkr_reply_id` 和 `ibkr_reply_message`。
- 前端二次确认后再调用 confirm endpoint。

### 订单状态不同步

- 本地订单状态以 IBKR 查询结果为准。
- 增加后台 sync job 定期刷新 open orders。
- 如果本地有 submitted 但 IBKR 查不到，标记为 `unknown`，需要人工检查。

## 测试策略

### 单元测试

- `IBKRClient` HTTP 错误映射。
- `IBKRBroker` 账户字段映射。
- `IBKRBroker` 持仓字段映射。
- `ticker -> conid` 缓存。
- snapshot 空响应重试。
- MARKET / LIMIT 订单 payload。
- IBKR reply 转换为 `IBKROrderRequiresConfirmation`。
- 下单请求不自动重试。

### API 测试

- 未登录访问 `/broker/status` 返回 401。
- 普通用户访问下单 API 返回 403。
- operator 可以读取 status、positions。
- admin 可以 approve pending approval。
- Gateway offline 时下单返回 409。
- requires_confirmation 状态不能重复 approve，只能 confirm 或 reject。

### 前端测试

- Broker 状态页正确展示 offline / authenticated / ready。
- 审批页 pending approval 按状态展示按钮。
- IBKR warning 二次确认态不丢失 warning 文本。
- 403/409 错误展示为用户可理解的提示。

### 集成测试

使用 fake IBKR server：

- 模拟 `/tickle`。
- 模拟 auth status。
- 模拟 account summary。
- 模拟 positions。
- 模拟 secdef search。
- 模拟 marketdata snapshot 首次为空、第二次有价格。
- 模拟 order 成功。
- 模拟 order 返回 reply id。

不建议在 CI 里依赖真实 IBKR Gateway。

## 分阶段实施

### Phase 1：Gateway MVP

交付：

- `IBKRClient`
- `IBKRBroker`
- broker factory
- 配置项
- status / account / positions / orders 基础 API
- Gateway session monitor
- fake IBKR server 测试

成功标准：

- 本地或服务器 Gateway 登录后，后端能读到账户和持仓。
- `TRADINGBOT_BROKER=ibkr` 时 CLI 和 API 都能构造 broker。
- 无真实下单能力也可先合并。

### Phase 2：审批和 paper 下单

交付：

- `trade_approvals`
- `broker_orders`
- approval API
- IBKR what-if
- MARKET / LIMIT paper order
- IBKR reply 二次确认
- 前端审批页

成功标准：

- 分析结果可以生成待审批交易。
- admin 审批后提交 IBKR paper order。
- 订单和成交结果写入本地数据库。

### Phase 3：订单同步和 dashboard

交付：

- open order sync job
- order history API
- portfolio 页面接 broker positions
- broker status 页面
- 风控和性能页对接真实 broker 数据

成功标准：

- 前端能看到 IBKR 账户状态、持仓、订单状态。
- Gateway 掉线或 session 过期时，前端状态明确，系统禁止下单。

### Phase 4：OAuth 多用户接入

交付：

- `broker_connections.mode = oauth`
- OAuth callback
- token 加密存储
- per-user broker account scope
- token refresh
- 撤销授权

成功标准：

- 每个用户可以绑定自己的 IBKR 账户。
- 用户只能看到和操作自己的 broker connection。
- 平台级 Gateway 和用户级 OAuth 可以共存。

## 关键设计决策

### 决策 1：前端不直连 IBKR

原因：

- 保持统一鉴权、CSRF、风控和审计。
- 避免暴露 Gateway 地址。
- 适配服务端部署。

### 决策 2：第一阶段使用平台级 Gateway

原因：

- 当前系统是服务端运行，用户只访问前端。
- Gateway 登录限制决定它不适合作为每个远程用户的浏览器能力。
- 能最快验证 broker adapter 和交易闭环。

### 决策 3：下单先持久化审批，再执行

原因：

- agent 结果不能直接触达真实交易。
- 审批记录是合规和排障基础。
- IBKR reply 需要二次确认，天然适合状态机。

### 决策 4：IBKR API client 独立于 BrokerAdapter

原因：

- `IBKRBroker` 只负责业务模型映射。
- HTTP、限流、错误映射、session 处理集中在 client/session 文件。
- 后续 OAuth transport 替换时，不影响上层交易逻辑。

### 决策 5：OAuth 作为第二阶段，不混入 Gateway MVP

原因：

- OAuth 涉及产品、合规、token 安全和账户授权模型。
- 混在第一阶段会拖慢最小可用交易链路。
- 通过 `broker_connections` 和 client 边界保留演进空间即可。

## 运维说明

### Gateway 部署

建议：

- Gateway 与后端部署在同一台服务器。
- 使用 systemd 或 supervisor 管理 Gateway 进程。
- 后端只访问 `localhost` 或内网地址。
- 管理员通过受控方式访问 Gateway 登录页完成 2FA。

### 监控

需要监控：

- Gateway 进程是否存活。
- `/tickle` 是否成功。
- auth status。
- brokerage session 状态。
- IBKR API 429 数量。
- 下单失败数量。
- `requires_confirmation` 卡住数量。

### 故障处理

- Gateway offline：重启 Gateway。
- auth expired：管理员重新登录。
- brokerage session failed：调用 init，失败则重新登录。
- order unknown：后台 sync，仍 unknown 则人工去 IBKR Portal/TWS 核对。

## 开放问题

这些问题不阻塞第一阶段设计，但实施前需要确认：

- 第一阶段是否只允许 `admin` 下单，还是 `operator` 也可以下单。
- Gateway 部署在同一台服务器还是独立内网机器。
- 是否需要从一开始支持多个 IBKR account id。
- paper trading 验证通过后，live trading 是否仍强制人工审批。
- 是否要把 IBKR 下单能力接到现有 `run_analysis_task` 成功后的自动 proposal 生成，还是先只做手动从分析结果生成交易建议。

## 推荐默认值

- 第一阶段只启用 paper trading。
- 第一阶段 `admin` 和 `operator` 可查看，只有 `admin` 可最终提交订单。
- 第一阶段只配置一个 `IBKR_ACCOUNT_ID`。
- 第一阶段所有 IBKR reply 都手动确认。
- 第一阶段不自动把每个 analysis run 变成 approval；由用户在分析详情页点击“生成交易建议”。
