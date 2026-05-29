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
- 支持“每个用户绑定自己的 IBKR 账户”：用户在 IBKR 官方授权页登录和 2FA，后端保存该用户的授权 token。
- 用户和服务器不需要处在同一局域网；授权通过公网 OAuth callback 完成。
- Gateway 仅作为内部自营、开发验证或单账户部署模式，不作为远程用户授权方案。
- 所有真实下单默认需要人工审批，避免 agent 直接自动交易真实资金。

## 非目标

- 不要求远程用户安装或运行 Client Portal Gateway。
- 第一阶段不实现期权、期货、组合保证金、bracket order、复杂条件单。
- 第一阶段不实现 WebSocket 实时行情；用 REST snapshot 满足最小交易链路。
- 第一阶段不让前端直连 `https://localhost:5000/v1/api`。
- 不绕过 IBKR 的第三方 onboarding、合规审批和 2FA 要求。

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
- Web API / OAuth 是第三方平台和多用户授权的方向。官方 Web API 文档写明 OAuth 2.0 支持 first-party 和 third-party 场景，但处于 beta；同一页也写明 third-party vendors 目前只能申请 OAuth 1.0a。
- 第三方 vendors 需要先通过 IBKR onboarding、Compliance 审批和 Legal 协议流程，才能拿到 OAuth consumer 配置、public key 和 callback URL 配置。
- 第三方连接的用户账户需要满足 IBKR 要求：已开通账户、IBKR Pro、账户 funded，且 2FA 方法受支持。
- 交易功能仍涉及 brokerage session。一个 IB username 同时只能有一个 brokerage session，用户如果同时使用 TWS、IBKR Mobile 或其他 API，可能造成 session 竞争。

## 架构方案比较

### 方案 A：IBKR 第三方 OAuth，每个用户授权自己的账户

```
React SPA
  -> FastAPI /api
    -> BrokerConnectionService
      -> encrypted user OAuth token
      -> IBKROAuthBroker
        -> api.ibkr.com
          -> IBKR
```

特点：

- 用户不需要和服务器在同一局域网。
- 用户不需要安装 Gateway。
- 用户在 IBKR 官方授权页输入 IBKR credentials 和完成 2FA。
- 后端只保存用户授权 token，不接触用户 IBKR 密码。
- 每个系统用户都有自己的 `broker_connections` 记录，账户、持仓、订单按 `user_id` 隔离。
- 适合公网 SaaS 或多租户部署。

风险：

- 接入前必须走 IBKR 第三方 onboarding 和合规审批。
- 官方当前第三方 vendors 可申请的是 OAuth 1.0a；OAuth 2.0 虽是统一 Web API 方向，但仍需要按 IBKR 可用性落地。
- token、callback、state、防 CSRF、撤销授权都必须严谨实现。
- 用户的 IBKR brokerage session 可能与 TWS/移动端冲突，产品上必须解释。

结论：作为“用户隔离、服务端部署”的主方案。

### 方案 B：服务端部署 Client Portal Gateway，平台级 IBKR 账户

```
React SPA
  -> FastAPI /api
    -> BrokerService
      -> IBKRGatewayBroker
        -> IBKR Client Portal Gateway
          -> IBKR
```

特点：

- 实现最快，适合内部自营、单账户 paper trading、开发验证。
- Gateway 与后端运行在同一台服务器或同一内网。
- 前端只看到系统 API，不知道 IBKR Gateway 地址。

风险：

- 只能代表平台级或管理员级账户，不代表远程用户自己的账户。
- 管理员需要维护 Gateway 登录状态和 2FA。
- 不满足多用户隔离授权。

结论：保留为内部模式，不作为用户授权方案。

### 方案 C：每个用户本地运行 Gateway，浏览器连接本机

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

## 推荐方案

主线采用“方案 A：IBKR 第三方 OAuth，每个用户授权自己的账户”。Gateway 只作为内部/自营/开发验证模式。

推荐原因：

- 用户与服务器网络隔离时，Gateway 方案无法让用户授权自己的账户；OAuth callback 才是正确边界。
- 当前系统已有用户、session、CSRF、加密工具和 FastAPI API 层，适合承载 OAuth state、callback 和 token 加密存储。
- `BrokerAdapter` 仍然可复用，但 `IBKRBroker` 需要拆成 transport/session 抽象：OAuth transport 面向用户账户，Gateway transport 面向内部账户。
- 交易审批、风控、订单记录仍在后端统一完成，前端不直接碰 IBKR。

## 用户授权主流程

用户不在服务器局域网内时，授权流程不能依赖 Gateway。正确流程是 OAuth redirect：

```
用户浏览器
  -> 点击“连接 IBKR”
  -> FastAPI 创建 OAuth state / nonce
  -> 浏览器跳转到 IBKR 授权页
  -> 用户在 IBKR 官方页面登录 + 2FA + 同意授权
  -> IBKR redirect 到 https://你的域名/api/broker/ibkr/oauth/callback
  -> FastAPI 校验 state
  -> FastAPI 用 verifier/code 换取 token
  -> token 加密写入 broker_connections
  -> 后端调用 IBKR API 拉账户列表
  -> 用户选择默认交易账户
  -> 后续查询/交易都由后端带该用户 token 调 IBKR
```

关键点：

- 用户只需要能访问你的前端和 IBKR 官方授权页，不需要访问服务器内网。
- 后端 callback URL 必须是公网 HTTPS 地址，并提前在 IBKR onboarding 中登记。
- 前端不能拿到 OAuth access token、token secret、private key。
- OAuth `state` 必须绑定当前系统 session，防止登录 CSRF 和 token 串号。
- token 存储必须按 `user_id` 隔离；所有 broker API 默认只能读写当前用户自己的 connection。
- 用户撤销授权或 token 失效后，系统把 connection 标记为 `reauthorization_required`，前端提示重新连接。

### OAuth 1.0a 与 OAuth 2.0 的落地策略

IBKR 文档当前同时呈现两个现实：

- 统一 Web API 的目标授权方式是 OAuth 2.0，且说明支持 first-party 和 third-party。
- 第三方 vendors 当前只能申请 OAuth 1.0a，且需要 IBKR compliance onboarding。

因此实现层不要把业务绑定死在 OAuth 1.0a 或 OAuth 2.0 上，而是定义统一接口：

```python
class IBKRAuthProvider(Protocol):
    def authorization_url(self, user_id: str) -> str:
        raise NotImplementedError

    def handle_callback(
        self,
        user_id: str,
        params: Mapping[str, str],
    ) -> BrokerConnection:
        raise NotImplementedError

    def signed_request(
        self,
        connection: BrokerConnection,
        request: IBKRRequest,
    ) -> IBKRResponse:
        raise NotImplementedError
```

第一版实现 `IBKROAuth1Provider`。如果 IBKR 批准 OAuth 2.0 或后续第三方 OAuth 2.0 可用，再新增 `IBKROAuth2Provider`，不改上层 broker、审批和前端交易流程。

## 系统边界

### 前端边界

前端只负责：

- 展示 IBKR 连接状态。
- 展示账户、持仓、订单、待审批交易。
- 发起“预览订单”“批准订单”“取消订单”等业务动作。
- 发起“连接 IBKR”“重新授权 IBKR”“断开 IBKR”。
- 展示 token 失效、需要重新授权、brokerage session 冲突等状态提示。

前端不负责：

- 存储 IBKR 密钥或 token。
- 直接调用 IBKR Gateway。
- 直接调用 `api.ibkr.com`。
- 绕过后端风控下单。

### 后端边界

后端负责：

- 维护用户级 IBKR OAuth connection、token 状态和 brokerage session 状态。
- 统一封装 IBKR REST API。
- 统一处理 IBKR 错误、限流、reply 确认、行情字段映射。
- 调用现有风控和订单记录。
- 提供给前端的稳定业务 API。
- 记录审计日志：谁在什么时候批准了什么订单，提交结果是什么。

### OAuth 边界

OAuth provider 只负责：

- 生成授权 URL。
- 校验 callback state。
- 换取和刷新 token。
- 对 IBKR 请求签名或附加 bearer token。

OAuth provider 不负责：

- 做交易风控。
- 做订单审批。
- 决定交易数量。
- 写入投资组合记录。

这些业务仍由 `TradeApprovalService`、`TradeExecutionService`、`RiskGate` 和 `PortfolioManager` 负责。

### Gateway 边界

Gateway 只作为内部模式的 IBKR 官方本地代理：

- 不暴露给公网。
- 只允许后端所在主机或内网访问。
- 登录状态由管理员维护。
- 不用于远程用户授权。
- 内部模式通过后端健康检查展示给管理员。

## 功能范围

### 连接状态

系统提供 IBKR 连接状态：

- `connection_mode`：`oauth1`、`oauth2` 或 `gateway`。
- `connection_status`：`not_connected`、`pending_authorization`、`connected`、`reauthorization_required`、`degraded`。
- `authenticated`：OAuth token 是否可用。
- `brokerage_session`：`/iserver` 交易 session 是否可用。
- `session_conflict`：用户是否可能在其他 IBKR 平台占用了 brokerage session。
- `account_id`：当前选择账户。
- `paper`：当前是否 paper 环境。
- `last_checked_at`：最近一次状态检查时间。
- `last_error`：最近一次连接错误摘要。

Gateway 内部模式额外提供：

- `gateway_online`：Gateway HTTP 是否可访问。
- `last_tickle_at`：最近一次保活时间。

状态异常时：

- 禁止提交新订单。
- 允许查看系统内历史分析和本地数据库记录。
- OAuth 模式前端显示“需要重新授权 IBKR”。
- Gateway 内部模式前端显示“需要管理员重新登录 IBKR Gateway”。

### 账户和持仓

后端使用当前用户的 broker connection 获取：

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
  -> 前端展示当前用户自己的待审批订单
  -> 账户 owner 点击批准
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
        connection: BrokerConnection,
        client: IBKRClient,
        timeout_seconds: float = 10.0,
    ):
        self.connection = connection
        self.client = client
        self.timeout_seconds = timeout_seconds
```

关键方法：

- `health()`：返回 OAuth token、brokerage session 和账户状态。
- `ensure_brokerage_session()`：需要交易/行情前调用。
- `get_account()`。
- `get_positions()`。
- `get_position(ticker)`。
- `get_latest_price(ticker)`。
- `submit_order(ticker, qty, side, order_type, limit_price, time_in_force)`。
- `get_order(order_id)`。
- `cancel_order(order_id)`。
- `get_order_history(limit)`。

Gateway 内部模式可以复用同一 `IBKRBroker` 业务映射，但传入 `IBKRGatewayClient`。用户授权模式传入 `IBKROAuthClient`。

### IBKR API client

文件：

- `tradingbot/broker/ibkr_client.py`

职责：

- 封装 HTTP。
- 做 base URL 拼接：OAuth 模式使用 `https://api.ibkr.com/v1/api`，Gateway 内部模式使用配置的 Gateway URL。
- 做 request timeout。
- 做错误类型转换。
- 做简单限流。
- OAuth 模式对请求签名或附加 token。
- Gateway 内部模式处理 Gateway 自签证书。

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

client 形态：

- `IBKROAuthClient`：用户授权主线，从 `broker_connections` 读取加密 token，解密后签名请求。
- `IBKRGatewayClient`：内部模式，访问 `IBKR_BASE_URL`，只用于平台级账户或开发验证。

### connection/session monitor

文件：

- `tradingbot/broker/ibkr_session.py`

职责：

- 后台维护每个 broker connection 的 IBKR 状态。
- OAuth 模式定期校验 token 可用性、账户可读性和 brokerage session 状态。
- Gateway 内部模式每 60 秒调用 `/tickle`。
- 定期调用 auth/session status。
- 状态变化时写日志。
- 可被 FastAPI startup 初始化，也可被 scheduler 初始化。

状态机：

```
unconfigured
  -> not_connected
  -> pending_authorization
  -> authenticated
  -> brokerage_ready
  -> reauthorization_required
  -> degraded
```

状态说明：

- `unconfigured`：未配置 IBKR OAuth consumer 或未启用 ibkr。
- `not_connected`：当前用户没有 broker connection。
- `pending_authorization`：已开始授权但 callback 尚未完成。
- `authenticated`：token 可用但 brokerage session 未就绪。
- `brokerage_ready`：可以查询 `/iserver` 和提交订单。
- `reauthorization_required`：token 失效、用户撤销授权或 IBKR 要求重新授权。
- `degraded`：近期请求失败或限流严重，禁止新下单。

### broker factory

当前 `run_bot.py` 和 `tradingbot/dashboard/app.py` 各自构造 broker。第一阶段先保持小改动：

- 新增 `tradingbot/broker/factory.py`，集中 `build_broker(config)`。
- `run_bot.py`、dashboard、API broker router 共用 factory。
- 支持 `mock`、`alpaca`、`ibkr`。
- API 请求路径中，factory 使用当前 `user_id` 加载该用户的 active `broker_connections`。
- CLI/internal 路径中，factory 可以使用平台级 Gateway connection。

配置：

```env
TRADINGBOT_BROKER=ibkr
IBKR_AUTH_MODE=oauth1
IBKR_API_BASE_URL=https://api.ibkr.com/v1/api
IBKR_OAUTH_CONSUMER_KEY=<issued-by-ibkr>
IBKR_OAUTH_PRIVATE_KEY_PATH=/run/secrets/ibkr_private_key.pem
IBKR_OAUTH_CALLBACK_URL=https://app.example.com/api/broker/ibkr/oauth/callback
IBKR_ORDER_CONFIRMATION_MODE=manual
IBKR_PAPER=true
```

内部 Gateway 模式才使用：

```env
IBKR_AUTH_MODE=gateway
IBKR_BASE_URL=https://localhost:5000/v1/api
IBKR_ACCOUNT_ID=U1234567
IBKR_VERIFY_SSL=false
IBKR_AUTO_TICKLE=true
```

`IBKR_VERIFY_SSL=false` 是因为本地 Gateway 常见自签证书。只允许在 Gateway 不暴露公网时使用，且只用于内部模式。

### FastAPI broker router

文件：

- `tradingagents/api/routers/broker.py`

路由：

- `GET /broker/status`
- `GET /broker/connections`
- `POST /broker/ibkr/oauth/start`
- `GET /broker/ibkr/oauth/callback`
- `POST /broker/connections/{connection_id}/disconnect`
- `POST /broker/connections/{connection_id}/select-account`
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

- 普通登录用户可以连接、断开、查看和操作自己的 IBKR connection。
- 普通登录用户可以查看自己账户的持仓、订单和待审批交易。
- 普通登录用户可以批准自己账户的 pending approval。
- `admin` 可以查看连接健康摘要，但默认不能代表用户下单，除非后续设计显式增加 delegated trading 权限。
- 内部 Gateway 模式的最终下单默认只允许 `admin`。

CSRF：

- 所有 `POST` 路由沿用现有 CSRF 中间件。

### 数据模型

新增表建议：

#### `broker_connections`

保存用户授权状态。不保存 IBKR 密码；OAuth token 只保存加密密文。

字段：

- `connection_id`
- `user_id`
- `broker`：`ibkr`
- `mode`：`oauth1`、`oauth2` 或 `gateway`
- `account_id`
- `display_name`
- `paper`
- `status`
- `oauth_token_encrypted`
- `oauth_token_secret_encrypted`
- `refresh_token_encrypted`
- `token_expires_at`
- `scopes`
- `ibkr_username_hash`
- `last_checked_at`
- `last_error`
- `created_at`
- `updated_at`

约束：

- `(user_id, broker, mode, account_id)` 唯一。
- token 字段按 OAuth 版本使用；OAuth 1.0a 使用 token + token secret，OAuth 2.0 使用 access token + refresh token。
- Gateway 内部模式可用 `user_id = 'platform'` 或单独 `owner_type = platform` 表示平台级连接。

#### `trade_approvals`

保存 agent 生成但尚未提交的交易建议。

字段：

- `approval_id`
- `run_id`
- `user_id`
- `connection_id`
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
- `user_id`
- `connection_id`
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
- 登录用户可见自己的 Broker 页面。
- `admin` 额外可见平台连接健康摘要。

### Broker 状态页

展示：

- 当前 broker：Mock / Alpaca / IBKR。
- OAuth 连接状态。
- Brokerage session 状态。
- 当前账户。
- Paper/live 标识。
- 最近错误。
- 最近检查时间。
- Gateway 状态仅在内部模式展示。

操作：

- 连接 IBKR。
- 重新授权。
- 断开连接。
- 选择默认 account id。
- 刷新状态。
- 初始化 brokerage session。
- OAuth 模式跳转到 IBKR 官方授权页；不在前端嵌入 IBKR 登录页。
- Gateway 内部模式只显示“去服务器登录 Gateway”的说明。

### 持仓页

复用现有占位页面 `/portfolio`，改为调用 `/broker/positions`。

数据范围：

- 普通用户只看自己的 active broker connection。
- admin 可以在管理页看平台级连接，但默认不跨用户展示个人账户明细。

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
- 新增 `BrokerConnectionService` 负责按当前 `user_id` 解析 active IBKR connection。

流程：

```
AnalysisRun succeeded
  -> TradeProposalBuilder 从 result.decision/final_state 生成 proposal
  -> SignalMapper 映射 BUY/SELL/HOLD
  -> RiskGate 初审
  -> TradeApprovalService.create_pending()
  -> 当前账户 owner 在前端审批
  -> TradeExecutionService.execute_approved()
  -> BrokerConnectionService.load_active(user_id)
  -> IBKRBroker.submit_order()
  -> PortfolioManager.record_trade()
```

第一阶段可以只让手动触发的交易建议进入审批表，不自动把所有分析 run 都变成交易建议。这样降低误交易风险。

## 安全设计

### 网络

- OAuth callback 必须使用公网 HTTPS 地址。
- 后端访问 IBKR Web API 必须使用 HTTPS。
- Gateway 只用于内部模式；如果启用 Gateway，仍只监听本机或私有网络，不把 Gateway 端口暴露到公网。
- 如果内部模式下后端和 Gateway 不在同一台机器，必须走私有网络或 SSH tunnel，不通过公网明文访问。

### 认证和权限

- 前端沿用当前 session cookie + CSRF。
- broker API 全部需要登录。
- 普通用户只能管理自己的 broker connection，不能访问其他用户账户。
- 普通用户只能批准自己账户的交易建议。
- `admin` 默认只有平台管理和健康查看权限，不默认拥有代用户下单权限。
- OAuth callback 必须校验 `state`、session 绑定和过期时间。

### 秘密和 token

系统不保存 IBKR 密码。

OAuth token：

- 复用 `tradingagents/api/crypto.py` 的 Fernet 加密能力。
- token 只保存密文。
- refresh token 和 access token 分开记录。
- 所有 token 解密只发生在后端请求 IBKR 前。
- OAuth private key 使用文件或 secret manager 注入，不入库，不提交到 git。

Gateway 内部模式：

- 不在系统中保存 Gateway 登录密码。
- 管理员通过 IBKR 官方登录流程完成 2FA。

### 真实交易保护

- `IBKR_PAPER=true` 作为默认。
- live 模式启动时要求显式 `IBKR_PAPER=false`。
- live 模式默认强制人工审批。
- live 模式禁止自动确认 IBKR reply。
- 下单前二次读取账户和价格，避免审批后市场变化导致超额下单。
- 所有订单写入本地数据库，便于追踪。

## 错误处理

### 未连接 IBKR

- `GET /broker/status` 返回 `not_connected`。
- 下单返回 `409 broker connection required`。
- 前端显示“连接 IBKR”。

### OAuth token 失效或被撤销

- 状态返回 `reauthorization_required`。
- 禁止下单。
- 前端显示“需要重新授权 IBKR”。

### Brokerage session 未就绪

- 后端尝试初始化 brokerage session。
- 如果仍失败，状态返回 `authenticated` 但 `brokerage_session=false`。
- 禁止交易接口。
- 如果 IBKR 返回 session conflict，前端提示用户可能需要退出 TWS、IBKR Mobile 或其他 API session。

### Gateway 离线

- 仅内部模式适用。
- `GET /broker/status` 返回 `gateway_offline`。
- 下单返回 `409 broker unavailable`。
- 前端显示“Gateway 未连接，需要管理员检查服务”。

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

- OAuth start 生成 state 并绑定当前 user session。
- OAuth callback 拒绝错误 state、过期 state、跨用户 state。
- token 加密落库，响应中不暴露明文 token。
- `IBKROAuthClient` 正确签名请求。
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
- 用户只能读取自己的 broker connection。
- 用户不能读取其他用户的 positions、orders、approvals。
- 用户可以 start OAuth 并完成自己的 callback。
- 用户可以 approve 自己账户的 pending approval。
- 未连接 IBKR 时下单返回 409。
- requires_confirmation 状态不能重复 approve，只能 confirm 或 reject。

### 前端测试

- Broker 状态页正确展示 not connected / connected / reauthorization required / ready。
- Connect IBKR 按钮跳转后端 OAuth start endpoint。
- 重新授权状态显示明确入口。
- 审批页 pending approval 按状态展示按钮。
- IBKR warning 二次确认态不丢失 warning 文本。
- 403/409 错误展示为用户可理解的提示。

### 集成测试

使用 fake IBKR server：

- 模拟 OAuth request token / access token / callback。
- 模拟 auth status。
- 模拟 account summary。
- 模拟 positions。
- 模拟 secdef search。
- 模拟 marketdata snapshot 首次为空、第二次有价格。
- 模拟 order 成功。
- 模拟 order 返回 reply id。

不建议在 CI 里依赖真实 IBKR Gateway。

## 分阶段实施

### Phase 0：IBKR 第三方接入准备

交付：

- 完成 IBKR third-party onboarding 申请。
- 明确当前可获批的 OAuth 版本：OAuth 1.0a 或 OAuth 2.0。
- 准备公网 HTTPS callback URL。
- 准备 OAuth public/private key 或 client secret。
- 明确允许的功能范围：read-only、trading、market data。

成功标准：

- IBKR 提供可用于测试/生产的 consumer 配置。
- callback URL 在 IBKR 侧配置完成。
- 明确第三方连接的账户要求和合规限制。

### Phase 1：OAuth 连接和账户只读 MVP

交付：

- `broker_connections`
- `IBKRAuthProvider`
- `IBKROAuth1Provider` 或 `IBKROAuth2Provider`
- OAuth start / callback / disconnect API
- token 加密存储
- status / accounts / account / positions API
- 前端 Broker 连接页
- fake IBKR OAuth server 测试

成功标准：

- 用户在公网前端点击“连接 IBKR”后，被跳转到 IBKR 授权页。
- callback 完成后，系统保存该用户的加密 connection。
- 用户能看到自己的 IBKR 账户和持仓。
- 用户不能看到其他用户的 broker connection。

### Phase 2：交易建议、审批和 paper 下单

交付：

- `trade_approvals`
- `broker_orders`
- TradeApprovalService
- TradeExecutionService
- IBKR what-if
- MARKET / LIMIT paper order
- IBKR reply 二次确认
- 前端审批页

成功标准：

- 分析结果可以为当前用户生成待审批交易。
- 当前账户 owner 审批后提交 IBKR paper order。
- 订单和成交结果写入本地数据库。
- IBKR reply 需要二次确认时，前端展示 warning，用户确认后才继续。

### Phase 3：订单同步和 dashboard

交付：

- open order sync job
- order history API
- portfolio 页面接 broker positions
- broker status 页面
- 风控和性能页对接真实 broker 数据

成功标准：

- 前端能看到当前用户的 IBKR 账户状态、持仓、订单状态。
- token 失效、session 冲突或 brokerage session 过期时，前端状态明确，系统禁止下单。

### Phase 4：内部 Gateway 模式可选补充

交付：

- `IBKRGatewayClient`
- Gateway session monitor
- 平台级 connection
- 内部 admin-only status 页面

成功标准：

- 内部自营或开发环境可以用 Gateway 跑单账户 paper trading。
- Gateway 模式与用户 OAuth 模式共存，但不会被远程用户授权流程使用。

## 关键设计决策

### 决策 1：前端不直连 IBKR

原因：

- 保持统一鉴权、CSRF、风控和审计。
- 避免暴露 Gateway 地址。
- 适配服务端部署。

### 决策 2：用户授权使用 OAuth，不使用 Gateway

原因：

- 用户与服务器网络隔离，Gateway 无法代表每个远程用户完成授权。
- OAuth redirect 是浏览器、第三方平台、IBKR 之间正确的授权边界。
- Gateway 只能作为内部平台账户模式，不能作为多用户账户连接方案。

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

### 决策 5：OAuth 版本通过 provider 抽象隔离

原因：

- IBKR 文档同时存在 OAuth 1.0a 第三方现实和 OAuth 2.0 统一方向。
- provider 抽象允许先落地 OAuth 1.0a，后续切 OAuth 2.0 不影响 broker、审批和前端交易流程。
- token 存储、用户隔离、审计和交易服务不应依赖具体 OAuth 版本。

## 运维说明

### OAuth 配置

建议：

- callback URL 使用公网 HTTPS。
- OAuth private key 或 client secret 放在 secret manager 或受控文件路径。
- 按环境拆分 staging / production callback URL。
- 定期验证 OAuth consumer 配置仍然有效。

### Gateway 部署

仅内部模式需要：

- Gateway 与后端部署在同一台服务器。
- 使用 systemd 或 supervisor 管理 Gateway 进程。
- 后端只访问 `localhost` 或内网地址。
- 管理员通过受控方式访问 Gateway 登录页完成 2FA。

### 监控

需要监控：

- OAuth callback 成功率。
- OAuth state 校验失败次数。
- token 解密失败次数。
- token 失效和重新授权数量。
- auth status。
- brokerage session 状态。
- IBKR API 429 数量。
- 下单失败数量。
- `requires_confirmation` 卡住数量。
- Gateway 进程和 `/tickle` 仅内部模式监控。

### 故障处理

- OAuth callback failed：检查 callback URL、state、consumer 配置和服务器时间。
- token expired/revoked：提示用户重新授权。
- brokerage session failed：调用 init，失败则重新登录。
- Gateway offline：仅内部模式，重启 Gateway。
- order unknown：后台 sync，仍 unknown 则人工去 IBKR Portal/TWS 核对。

## 开放问题

这些问题不阻塞设计，但实施前需要确认：

- IBKR 当前给该项目批准 OAuth 1.0a 还是 OAuth 2.0。
- 第三方审批周期和需要提交的产品材料。
- 普通用户是否可以自行批准自己账户的交易，还是需要额外平台审核。
- 是否需要从一开始支持一个 IBKR username 下多个 account id。
- paper trading 验证通过后，live trading 是否仍强制人工审批。
- 是否要把 IBKR 下单能力接到现有 `run_analysis_task` 成功后的自动 proposal 生成，还是先只做手动从分析结果生成交易建议。

## 推荐默认值

- 主线先做用户 OAuth 连接和只读账户/持仓。
- 下单阶段先启用 paper trading。
- 当前账户 owner 可批准自己账户的 paper order。
- live trading 仍强制人工审批。
- 所有 IBKR reply 都手动确认。
- 第一版不自动把每个 analysis run 变成 approval；由用户在分析详情页点击“生成交易建议”。
- Gateway 只作为内部模式，不作为用户授权入口。
