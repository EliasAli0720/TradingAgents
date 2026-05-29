# IBKR TWS API 接入设计（单一平台账户）

日期：2026-05-29

> 本文是 TWS API（socket）路线的独立设计，对应**单一平台账户**模型。
> 多用户、每人各自 IBKR 账户的 OAuth 路线见 `2026-05-29-ibkr-integration-design.md`（Web API / Client Portal API）。两份文档对应两种账户模型，不冲突。

## 背景

当前系统已有两条相关能力：

- 分析服务：FastAPI 后端位于 `tradingagents/api/`，Celery + Redis worker 位于 `tradingagents/worker/`，React 前端位于 `web/src/`，前端统一通过 `/api` 调后端。
- 交易执行：`tradingbot/broker/base.py:66` 定义 `BrokerAdapter`，现有 `MockBroker`、`AlpacaBroker` 已经把账户、持仓、行情、下单封装成统一同步接口（`get_account` / `get_positions` / `submit_order` / `get_order` / `cancel_order` / `get_order_history` / `get_latest_price`）。`AutoTrader`（`tradingbot/scheduler/runner.py:33`）把分析信号经 `SignalMapper` → `RiskGate` → `BrokerAdapter` → `PortfolioManager` 串成执行链路。

部署现状：**API 全部在服务端、用户与服务端隔离、用户机器上只有前端**。本设计的目标是把 IBKR 作为新的 broker backend 接入，让分析、风控、审批、下单、持仓展示仍走统一后端，用户**永远不直接接触 IBKR**。

## 为什么这条路线用 TWS API 而不是 Web API

账户模型是**单一平台账户**（自营 / 一个基金账户 / 团队共用账户），不是“每个登录用户绑定自己的 IBKR 账户”。在这个前提下：

- TWS API 与“服务端运行、用户只有前端”的部署**完美契合**：IB Gateway（headless）和后端跑在同一台服务器或同内网，用户在浏览器里只看前端 → 打后端 `/api` → 后端通过 socket 连本机 Gateway。
- TWS API **无需** IBKR 第三方 OAuth onboarding（省掉 3–6 周合规审批），功能最全（`whatIfOrder` 预览、bracket、stop、期权期货等后续可扩展），官方 `ibapi` + 成熟社区库 `ib_async`。
- 单账户场景下 TWS API 的最大短板（每个 IB 登录要一个 GUI Gateway、不能 per-user）不构成问题，因为只有一个账户、一个登录、一个 Gateway。

> 反过来，如果将来要做“每用户自己账户”的多租户，TWS API 不可行（要替每个用户保管 IB 密码、跑 N 个 headless GUI、处理 N 份 2FA），那时切到 Web API / OAuth 路线。本设计把 broker 层做成可切换 transport，为那一天留口子。

## 目标

- 接入 TWS API，让系统可以查询 IBKR 账户、持仓、行情、订单，并能下单。
- 支持服务端部署：headless IB Gateway 与后端同机/同内网，用户只访问前端。
- 复用现有 `BrokerAdapter`、`RiskGate`、`PortfolioManager`、`SignalMapper`、FastAPI 鉴权和 React 前端结构。
- 用一个**独占 IB socket 的连接进程**解决“持久有状态连接 + 单 brokerage session + 多进程后端”的根本矛盾。
- 所有真实下单默认需要人工审批；live 下单默认仅 `admin` 可批准。

## 非目标

- 不做多用户、每人各自 IBKR 账户（那是 OAuth 路线）。
- 第一阶段不做期权、期货、组合保证金、bracket、stop / stop-limit、条件单、fractional shares。
- 第一阶段不把 IBKR 行情作为 TradingAgents 历史分析数据源；分析数据仍走现有 `tradingagents/dataflows/`。
- 不把 headless Gateway 端口暴露公网。
- 第一阶段不追求 tick 级实时行情，REST/snapshot 级别满足最小交易链路即可。

## 官方约束摘要（TWS API）

来源：

- TWS API 文档：`https://interactivebrokers.github.io/tws-api/`（campus 入口 `https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/`）

约束：

- 客户端（`ibapi` 的 `EClient`/`EWrapper`，或 `ib_async`）通过**持久 socket** 连接 **TWS 桌面端**或 **IB Gateway**——两者从 API 视角等价，都是“一个可被 socket 连接的本地服务”。
- 默认端口：TWS `7496`（live）/ `7497`（paper）；IB Gateway `4001`（live）/ `4002`（paper）。端口可改。
- **官方明确不支持 headless 运行**：必须有 GUI、必须手动在登录窗口输入账号密码。服务器上只能靠 IBC + Xvfb/VNC + Docker（如 `gnzsnz/ib-gateway-docker`）这类**非官方 workaround**，通常要求**关闭/降级 2FA**，并配置**每日定时重启**（IBC `autoRestartTime`）。
- 需要在 TWS 里开启 “Enable ActiveX and Socket Clients”；IB Gateway 默认接受连接。
- **一个 IB username 同一时刻只有一个 brokerage session**。可以用不同 `clientId` 挂多个 API 客户端到同一个 Gateway，但都是同一个账户。如果同时在 TWS / IBKR Mobile / 其他 API 登录同一账户，会发生 session 竞争。
- `clientId=0`（master client）可收到该 Gateway 下所有客户端下单的订单与成交回报。
- 订单状态、成交、持仓更新是**事件回调推送**（`orderStatus` / `execDetails` / `openOrder` / `position`），不是请求-响应轮询。
- 行情需要账户具备对应市场数据订阅权限；无实时订阅时可用延迟行情（`reqMarketDataType(3=delayed / 4=delayed-frozen)`）。
- Gateway/TWS 每天有一次维护重启（server reset），重连后需重新拉取订单/持仓做对账。

## 核心架构：独占连接进程 + Redis 命令通道 + DB 镜像

TWS API 与 Alpaca 的本质区别是**有状态长连接 + 单 session + 事件驱动**。后端是多进程（多个 uvicorn worker + 多个 Celery worker + scheduler），不能让每个进程各开一条 socket 抢 `clientId`、抢唯一的 brokerage session。

方案：**有且仅有一个进程持有 IB socket 连接**（称作 **IBKR Connector**），其它进程通过 Redis 下发命令、通过共享 DB 读状态。

```
React SPA (浏览器)
  -> FastAPI /api/broker/*        鉴权 / CSRF / 审批 / 风控；不碰 socket
       |  下发命令 (Redis)              ^ 读 DB 镜像 (账户/持仓/订单/状态)
       v                                |
  IBKR Connector (单进程, 独占 socket)  --+--> 写 DB 镜像
       |  ib_async 长连接 + 事件回调
       v
  IB Gateway (headless, IBC, :4002 paper)   <- 同机 / 同内网
       v
     IBKR
```

要点：

- **Connector 唯一持有连接**，固定一个 `clientId`（建议 master `clientId=0` 以收全量订单回报），跑一个持续的 asyncio 事件循环：维护连接、自动重连、订阅 `orderStatusEvent` / `execDetailsEvent` / `openOrderEvent` / `positionEvent`，把变化**写进 DB 镜像表**（`broker_orders` 等）。
- **命令通道用 Redis**（系统已用 Redis 作 Celery broker）：FastAPI / Celery 把“下单 / 撤单 / 预览 / 拉账户”作为命令推到 Redis（list 或 stream），Connector 取出，经 ib_async 执行，把结果写回（DB + 一个 per-command 的 Redis 回执 key 供同步调用方等待）。
- **状态读取走 DB**：`/broker/status`、`/broker/account`、`/broker/positions`、`/broker/orders` 默认读 DB 镜像（Connector 周期刷新 + 事件更新），不每次穿透到 IBKR。需要强一致时才下发一次“刷新”命令。
- 这样**单 session 约束**（唯一 socket）与**多进程后端**（FastAPI/Celery/scheduler 横向扩展）同时满足。

> 单进程本地模式（CLI / 本机开发）可以让 `IBKRBroker` 直接连本机 Gateway，无需 Connector。但**不能与 Connector 同时连同一个 Gateway 登录**（单 session 竞争）。本地直连必须用不同 `clientId` 且不与服务端并存。

## 系统边界

### 前端边界

前端只负责：

- 展示 IBKR 连接状态（Gateway 在线、brokerage session、当前账户、paper/live、最近错误、最近检查时间）。
- 展示账户、持仓、订单、待审批交易。
- 发起“预览订单 / 批准订单 / 拒绝 / 撤单 / 确认”等业务动作，以及“刷新状态”。

前端不负责：直接连 socket / Gateway、绕过后端风控下单、保管任何 IBKR 凭证。

### 后端边界

后端负责：统一封装 IBKR、维护连接/会话状态、错误与限流处理、二次风控、订单审批与执行、订单/成交落库、审计、给前端稳定业务 API。

### Connector 边界

Connector 只负责：持有并维护 IB 连接；执行命令通道里的 broker 操作；把订单/成交/持仓事件写进 DB。
Connector 不负责：风控、审批、决定数量、写投资组合业务记录——这些仍在 `TradeExecutionService` / `RiskGate` / `PortfolioManager`。

### Gateway 边界

headless IB Gateway 只监听 `localhost` 或私有网络，不暴露公网；IB 登录凭证只存在于 Gateway/IBC 的环境变量或 secret，不入应用 DB。

## 后端设计

### 1. broker adapter：`tradingbot/broker/ibkr.py`

与 `AlpacaBroker` 平级，实现 `BrokerAdapter`，把统一模型映射到 IBKR。采用 `alpaca.py` 同款**惰性导入**（`ib_async` 仅在用到时 import，避免无依赖环境报错）。

```python
class IBKRBroker(BrokerAdapter):
    def __init__(self, conn: "IBKRConnection", account_id: str | None = None,
                 paper: bool = True, market_data_type: int = 3):
        self._conn = conn          # 持有/代理一条 ib_async 连接
        self._account_id = account_id
        self._paper = paper
```

实现：`get_account` / `get_positions` / `get_position` / `submit_order` / `get_order` / `cancel_order` / `get_order_history` / `get_latest_price`，外加：

- `health()`：Gateway 是否可连、brokerage session 是否就绪、当前账户、paper/live、最近错误。
- `preview_order(...)`：`ib.whatIfOrder(contract, order)` 返回保证金/手续费/初始与维持保证金影响，供审批前展示。

字段映射（IBKR → 现有 `base.py` 模型）：

- `AccountInfo.cash` ← `AvailableFunds`（缺失用 `TotalCashValue`）
- `AccountInfo.portfolio_value` ← `NetLiquidation`
- `AccountInfo.buying_power` ← `BuyingPower`
- `AccountInfo.equity` ← `NetLiquidation`
- `Position.avg_entry_price` ← `avgCost`
- `Position.current_price` ← `marketPrice`（缺失用 snapshot last）
- `Position.unrealized_pnl` ← `unrealizedPNL`（缺失本地算）
- `Order.status` ← IBKR `orderStatus.status`（`PendingSubmit/PreSubmitted/Submitted` → `PENDING`，`Filled` → `FILLED`，`Cancelled/ApiCancelled` → `CANCELLED`，`Inactive` → `REJECTED`），参考 `alpaca.py:22` 的 `_to_order_status` 写法。

### 2. 连接抽象：`tradingbot/broker/ibkr_connection.py`

把“怎么跟 IB 通信”从“业务映射”里分离，便于单测和将来切 transport。

```python
class IBKRConnection(Protocol):
    def ensure_connected(self) -> None: ...
    def qualify(self, symbol: str) -> Contract: ...          # conid 解析 + 缓存
    def account_summary(self, account_id: str) -> dict: ...
    def positions(self, account_id: str) -> list: ...
    def snapshot(self, contract) -> dict: ...                # last/bid/ask
    def place(self, contract, order) -> str: ...             # 返回 broker order id
    def what_if(self, contract, order) -> dict: ...
    def cancel(self, order_id: str) -> bool: ...
    def open_orders(self) -> list: ...
    def completed_orders(self) -> list: ...
    def health(self) -> dict: ...
```

两种实现：

- `LocalIBKRConnection`：进程内直接用 `ib_async.IB()`，自动重连，注册事件回调写 DB。Connector 进程与本地 CLI 模式用它。
- `RedisIBKRConnection`：FastAPI / Celery 用它——把方法调用序列化成命令推到 Redis，等 Connector 回执；只读查询直接读 DB 镜像，写操作走命令通道。

`IBKRBroker` 只依赖 `IBKRConnection` 协议，不关心是本地还是代理。

### 3. Connector 进程：`tradingbot/broker/ibkr_connector.py` + 启动器 `run_broker.py`

职责：

- 启动时 `IB().connect(host, port, clientId)`，断线自动重连（`ib_async` 的 `disconnectedEvent` + 退避重连）。
- 注册事件回调：`orderStatusEvent` / `execDetailsEvent` / `openOrderEvent` → upsert `broker_orders`；`positionEvent` → 刷新持仓镜像。
- 主循环消费 Redis 命令队列（下单 / 撤单 / 预览 / 强制刷新），执行后写 DB + 回执。
- 周期任务：每 N 秒拉 `reqOpenOrders` / 账户摘要刷新 DB；重连后做一次全量对账（`reqCompletedOrders`）。
- 健康状态（Gateway 在线、session 状态、最近错误、最近刷新时间）写入 `broker_status` 单行表。

用 systemd / supervisor / docker-compose 服务管理，**只跑一个实例**。

### 4. broker factory：`tradingbot/broker/factory.py`

现在 `run_bot.py:43` 和 `tradingbot/dashboard/app.py:81` 各自 `if/else` 造 broker。集中成 `build_broker(config, *, mode="local"|"server")`：

- 支持 `mock` / `alpaca` / `ibkr`。
- `ibkr` + `server`：返回 `IBKRBroker(RedisIBKRConnection(...))`。
- `ibkr` + `local`：返回 `IBKRBroker(LocalIBKRConnection(...))`（CLI / dashboard 单机）。
- `run_bot.py`、dashboard、API、Connector 共用此 factory。

### 5. FastAPI broker router：`tradingagents/api/routers/broker.py`

在 `tradingagents/api/app.py:23` 处 `app.include_router(broker.router)`（前缀 `/broker`）。路由：

- `GET /broker/status`
- `GET /broker/account`
- `GET /broker/positions`
- `GET /broker/orders`、`GET /broker/orders/{order_id}`
- `POST /broker/orders/preview`（whatIf）
- `POST /broker/orders`（人工手动下单：仅 `IBKR_APPROVAL_ROLE`，仍走 RiskGate + whatIf + 审计落库；下单人即审批人，不经过 `trade_approvals` 双人审批。与 agent 建议→审批流是两个独立的订单来源）
- `POST /broker/orders/{order_id}/cancel`
- `POST /broker/refresh`（下发一次强制刷新命令）
- `GET /broker/approvals`、`POST /broker/approvals/{id}/approve` / `reject`
- 复用现有 session cookie 鉴权 + CSRF 中间件（所有 `POST`）。

权限（单账户特性）：

- 普通登录用户：查看状态/账户/持仓/订单、生成交易建议（写 `trade_approvals`）。
- **真实下单/批准默认仅 `admin`**（因为是平台共用的同一个账户，下单影响所有人）。paper 环境可放宽到允许普通用户批准，由 `IBKR_APPROVAL_ROLE` 配置。

### 6. 数据模型（`tradingagents/api/db.py`，additive schema）

走现有 `Base.metadata.create_all` + `ensure_additive_schema` 增量加表，不破坏现有库。

单账户场景**不需要** per-user OAuth token 表；改为：

#### `broker_status`（单行/单账户健康）
`id`(固定) · `broker`(ibkr) · `gateway_online` · `brokerage_session` · `account_id` · `paper` · `last_refresh_at` · `last_error` · `updated_at`

#### `trade_approvals`（agent 生成、待审批的交易建议）
`approval_id` · `run_id` · `requested_by_user_id` · `ticker` · `conid` · `side` · `order_type` · `quantity` · `limit_price` · `time_in_force` · `estimated_price` · `estimated_value` · `whatif_init_margin` · `whatif_commission` · `risk_verdict` · `agent_reasoning` · `status`(`pending`/`approved`/`rejected`/`submitted`/`failed`/`expired`) · `approved_by_user_id` · `approved_at` · `submitted_order_id` · `created_at` · `updated_at`

#### `broker_orders`（IBKR 订单/成交镜像，由 Connector 写）
`broker_order_id`(IBKR permId/orderId) · `approval_id` · `account_id` · `ticker` · `conid` · `side` · `order_type` · `quantity` · `limit_price` · `time_in_force` · `status` · `filled_qty` · `filled_avg_price` · `submitted_at` · `updated_at` · `raw_event`

可选 append-only `broker_audit_events`（谁、何时、批准/下单了什么、结果），用于合规与排障。

### 7. 与 AutoTrader / 审批的结合

`AutoTrader`（`tradingbot/scheduler/runner.py:33`）现在 `require_approval=True` 时用阻塞 `input()`（`runner.py:283`）做审批——**服务端不能阻塞输入**。拆分：

- `AutoTrader.run_single()` 保留：分析 → 映射 → 风控初审。
- 新增 `TradeApprovalService`：把建议持久化为 `trade_approvals(status=pending)`。
- 新增 `TradeExecutionService.execute_approved(approval_id)`：二次读价/账户 → `RiskGate` 二次校验 → `IBKRBroker.preview_order`（whatIf）→ 通过命令通道 `submit_order` → 写 `broker_orders` + `PortfolioManager.record_trade`。

```
AnalysisRun succeeded
  -> TradeProposalBuilder（从 result.decision / final_state 生成 proposal）
  -> SignalMapper（BUY/SELL/HOLD → OrderInstruction）
  -> RiskGate 初审
  -> TradeApprovalService.create_pending()
  -> 前端展示待审批（whatIf 预览 + 风控结论）
  -> admin(或配置角色) 批准
  -> TradeExecutionService.execute_approved()
  -> IBKRBroker.submit_order() 经 Connector -> IB Gateway
  -> 事件回调 upsert broker_orders；PortfolioManager.record_trade()
```

第一阶段：**只让用户在分析详情页手动“生成交易建议”进入审批表**，不自动把每个 run 变成订单，降低误交易风险。

## 功能范围（第一阶段）

- 账户：summary（cash / net liquidation / buying power / equity）。
- 持仓：映射为现有 `Position`。
- 行情：`get_latest_price(ticker)` —— `qualifyContracts(Stock(sym,'SMART','USD'))` 解析 conid（缓存）→ snapshot last，缺失用 `(bid+ask)/2`；无实时订阅时 `reqMarketDataType(3)` 用延迟行情。仅美股整数股。
- 下单：BUY/SELL、MARKET/LIMIT、`DAY`/`GTC`、整数股；下单前 whatIf 预览；下单后查状态；撤单。
- 不做：fractional、option spread、bracket、stop/stop-limit、多账户批量。

## 配置（沿用 `tradingbot/config.py` 的 env 风格）

```env
TRADINGBOT_BROKER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=4002              # paper Gateway 4002 / live 4001 / TWS 7497/7496
IBKR_CLIENT_ID=0           # Connector 用 master client
IBKR_ACCOUNT_ID=DU1234567  # paper 账户
IBKR_PAPER=true            # 默认 paper；live 必须显式置 false
IBKR_READONLY=false        # ib_async 只读模式开关
IBKR_MARKET_DATA_TYPE=3    # 1 实时 / 3 延迟
IBKR_APPROVAL_ROLE=admin   # 谁能批准真实下单
IBKR_CMD_QUEUE=ibkr:commands   # Redis 命令通道
```

`paper_trading` 现在从 `ALPACA_PAPER` 推导（`tradingbot/config.py`），新增 broker 时把它泛化为 broker 无关的 `IBKR_PAPER` / `paper_trading`。

## headless Gateway 部署

加入 `docker-compose.yml` 一个服务（如 `gnzsnz/ib-gateway-docker`，内置 IBC）：

- 暴露 `4002`（paper）仅在 compose 内网，不映射到公网。
- env：`TWS_USERID` / `TWS_PASSWORD`（来自 secret，不入 git）、`TRADING_MODE=paper`、`IBC_AutoRestartTime` 每日定时重启、`TWOFA_TIMEOUT_ACTION=restart`。
- live 前需把 2FA 策略与 IBKR 沟通；workaround 不是官方支持，必须接受这点风险并加监控。
- Connector 与 Gateway 同 compose / 同主机，`IBKR_HOST` 指向服务名。

## 安全设计

- IB 凭证只在 Gateway/IBC（env/secret），**不入应用 DB**；`tradingagents/api/crypto.py` 的 Fernet 在本路线主要用于（如有）其它敏感配置，单账户 TWS 路线不存 OAuth token。
- Gateway 端口不出私网；Connector ↔ Gateway 走 `localhost`/内网。
- 前端沿用 session cookie + CSRF；broker API 全部需登录；真实下单默认 admin。
- 真实交易保护：`IBKR_PAPER=true` 默认；live 要显式 `false`；live 强制人工审批；下单前二次读价/账户避免审批后行情变化超额；所有订单落库；保留一个 `POST /broker/halt` kill-switch（Connector 拒绝新单）。

## 错误处理

- Gateway 离线 / 未连接：`/broker/status` → `gateway_offline`；下单返回 `409 broker unavailable`；前端提示“需要管理员检查 Gateway”。
- brokerage session 未就绪 / 竞争：状态标 `session_conflict`，禁交易接口，提示可能有 TWS/Mobile 占用同一账户。
- 行情无订阅权限：降级延迟行情并在响应里标 `delayed=true`。
- 下单失败：不自动重试（避免重复单）；写 `trade_approvals.status=failed` + 错误。
- 订单状态不同步：以 Connector 对账结果为准；本地有 submitted 但 IBKR 查不到 → 标 `unknown` 待人工核对。

## 测试策略

- **单元**：`IBKRBroker` 字段映射（account/position/order status）；conid 缓存；snapshot 空值回退 `(bid+ask)/2`；MARKET/LIMIT order payload；whatIf 解析；下单不自动重试。通过对 `IBKRConnection` 协议做 **Fake 实现**注入，不连真 Gateway。
- **API**：未登录 401；普通用户不能 live 下单（`IBKR_APPROVAL_ROLE`）；未连接时下单 409；审批状态机不可越权流转。
- **前端**：状态页 `gateway_offline/connected/session_conflict/ready`；审批页按状态出按钮；whatIf 预览展示；409/403 友好提示。
- **集成**：用 Fake Connector（消费 Redis 命令、返回预置回执、写 DB 镜像）跑“建议 → 审批 → 下单 → 镜像更新”全链路。**不在 CI 依赖真实 Gateway**；真 paper Gateway 验证作为手动冒烟。

## 分阶段实施

### Phase 0：headless paper Gateway 跑通
- docker-compose 起 IB Gateway（paper）+ IBC，配置每日重启。
- 验证 `ib_async` 能 `connect(4002)`、读 account summary、qualify 一个股票。
- 成功标准：本机脚本能稳定连上并读到 paper 账户余额。

### Phase 1：只读 MVP
- `IBKRConnection`（Local + Redis 两实现）、`IBKRBroker` 只读、Connector 进程、Redis 命令通道、`broker_status`/镜像表、factory。
- `GET /broker/status` / `account` / `positions`，前端 Broker 状态页 + 持仓页（复用 `/portfolio`）。
- 成功标准：前端能看到平台账户余额与持仓；Gateway 掉线时状态明确、禁止下单。

### Phase 2：审批 + paper 下单
- `trade_approvals` / `broker_orders`、`TradeApprovalService` / `TradeExecutionService`、whatIf 预览、MARKET/LIMIT paper 下单、事件回调 upsert、前端审批页。
- 成功标准：分析结果能生成待审批；批准后提交 paper 订单；成交回写库；全程用户不碰 IBKR。

### Phase 3：对账 + dashboard
- 重连全量对账、`reqOpenOrders` 周期刷新、订单历史 API、portfolio/risk/perf 页接真实 broker 数据。
- 成功标准：前端看到账户/持仓/订单状态；session 异常时禁止下单且状态清晰。

### Phase 4（后续，单独）：live 硬化
- live 切换（显式 `IBKR_PAPER=false` + 二次确认）、admin gate、kill-switch、监控告警、(可选) bracket/stop 扩展。

## 关键设计决策

1. **单进程独占 socket + Redis 命令通道 + DB 镜像**：唯一能同时满足“TWS 单 session”与“多进程后端”的结构；复用已有 Redis，不引入新中间件。
2. **`IBKRConnection` 协议隔离 transport**：Local 直连给 CLI/Connector，Redis 代理给 API/Worker；`IBKRBroker` 与上层 `AutoTrader`/factory 不感知差异，也为将来切 Web API/OAuth 留口子。
3. **下单先持久化审批再执行**：agent 结果不直达真实交易；审批/订单记录是合规与排障基础；服务端用状态机替代 `runner.py:283` 的阻塞 `input()`。
4. **真实下单默认 admin**：单账户是平台共用资金，下单影响所有人；paper 可按配置放宽。
5. **行情仅用于交易链路，不替换 dataflows**：分析历史数据仍走 `tradingagents/dataflows/`，避免引入 IBKR 行情订阅与权限耦合到分析侧。

## 运维说明

- Gateway 与 Connector 同机/同 compose；`systemd`/`supervisor`/`docker restart: always` 守护；Connector 只跑一个实例。
- 监控：Gateway 在线率、重连次数、brokerage session 状态、命令通道积压、下单失败数、卡在 `pending`/`unknown` 的审批与订单数、每日重启是否成功。
- 故障：Gateway offline → 重启容器；session conflict → 检查是否有 TWS/Mobile 登录同账户；order unknown → 重连对账，仍 unknown 则人工去 IBKR Portal/TWS 核对。

## 开放问题（实施前确认）

- 平台账户的市场数据订阅级别：用实时（要订阅、要权限）还是延迟行情起步？
- `clientId` 分配：Connector 固定 0；本地开发/CLI 用哪个区间，且如何避免与 Connector 抢同一登录的 session。
- live 下单是否一律 admin 双人确认；是否需要日内 kill-switch 阈值（连亏自动停）。
- scheduler 是否自动把 watchlist 分析结果转成待审批，还是第一版只允许用户手动从分析详情页生成。
- headless Gateway 的 2FA 策略：能否使用 IBKR 的免 2FA 例外/专用 API 用户，还是接受 workaround 风险。

## 推荐默认值

- 先做只读账户/持仓，再做 paper 下单。
- `IBKR_PAPER=true`、`IBKR_MARKET_DATA_TYPE=3`（延迟）、`IBKR_APPROVAL_ROLE=admin`。
- 所有 live 下单强制人工审批；第一版不自动把每个 analysis run 变成 approval。
- Connector 单实例、master `clientId=0`、Gateway 不出私网。
</content>
</invoke>
