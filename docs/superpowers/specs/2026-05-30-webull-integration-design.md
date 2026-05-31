# Webull 接入设计(存档,后续实施)

日期：2026-05-30
状态：**暂缓**——先完成 IBKR,Webull 留作后续。本文记录调研结论与实施方案,届时直接照做。

## 背景

系统已有 `BrokerAdapter` 抽象(`tradingbot/broker/base.py`),现有 `mock`/`alpaca`/`ibkr` 三个实现。本文评估把 **Webull** 作为第四个 broker 接入,以及现有系统的复用率。

结论先行:**Webull 能接,而且是四个里最省事的;现有系统对它几乎全部可复用,新代码基本只有一个 `WebullBroker` 适配器。**

## Webull OpenAPI 关键事实

来源:
- 概览 `https://developer.webull.com/apis/docs/trade-api/overview`
- 入门 `https://developer.webull.com/apis/docs/getting-started/`、SDK `https://developer.webull.com/apis/docs/sdk/`
- Connect API(OAuth)`https://developer.webull.com/apis/docs/connect-api/authentication/`
- Python SDK `https://github.com/webull-inc/openapi-python-sdk`

事实:

- **云端 REST + gRPC + MQTT,无需任何本地网关/软件**(与 IBKR TWS 本地 socket 截然相反)。本质像 Alpaca:发 HTTPS 请求即可。
- **官方 Python SDK**:`webull-inc/openapi-python-sdk`,自动处理签名。
- **能力**:账户余额、持仓、下单/改单/撤单(含批量)、订单类型(市价/限价/止损/止损限价/移动止损/算法 TWAP·VWAP·POV/组合 OTO·OCO·OTOCO)、gRPC 实时订单回报、MQTT 实时行情。美股(含碎股、做空)、期权、期货、加密、event contracts。
- **限速**:账户余额/持仓约 2 req/2s;下单约 600 req/60s(实现时按文档加客户端限流)。
- **两种鉴权模型:**
  - **Trading API**:`App Key + App Secret`(HMAC 签名),面向"用自己账户"的个人/量化。OpenAPI 管理页申请,审核约 **1–2 个工作日**;另有免申请的**测试环境 + 共享测试账户**可先开发。
  - **Connect API**:`OAuth 2.0`(美区 `https://us-oauth-open-api.webull.com/oauth-openapi/`,UAT `...uat.webullbroker.com`),面向"第三方平台让用户授权各自的 Webull 账户"。功能与 Trading API 完全一致,仅 base URL 不同。
- 区域相关:美区(本文目标);另有 webull.co.jp、Webull Pay(crypto)等独立端点。

## 与 IBKR 的本质区别 → Webull 跳过一大堆复杂度

| IBKR(本地 socket)需要 | Webull(云端 REST)需要 |
|---|---|
| 独占 socket 的 connector 进程(`run_broker.py`) | ❌ 不需要 |
| Redis 命令通道 / `RedisIBKRConnection` | ❌ 不需要 |
| 单 brokerage session / clientId 管理 | ❌ 不需要 |
| headless Gateway / 本地 TWS | ❌ 不需要 |
| 异步成交、事件回调镜像 | gRPC 订单回报可选;首版可轮询 |

Webull 是**无状态请求-响应**,直接调 SDK,和 `AlpacaBroker` 一个量级。

## 复用分析:几乎全部复用

**broker-无关、0 改动复用:**

- `tradingbot/broker/base.py` —— `BrokerAdapter` + 统一模型(`AccountInfo`/`Position`/`Order`/`OrderSide`/`OrderType`/`OrderStatus`)
- `tradingbot/risk/gate.py`(RiskGate)、`tradingbot/portfolio/manager.py`(PortfolioManager)、`tradingbot/broker/signal_mapper.py`
- `tradingbot/services/*` —— `TradeProposalBuilder` / `TradeExecutionService` / `BrokerConnectionService`
- `tradingagents/api/broker_repository.py` + `trade_approvals` / `broker_orders` 表
- `tradingagents/api/routers/broker.py` —— `/broker` 路由 + schemas(全程只调 `BrokerAdapter`)
- `web/src/api/broker.ts` + `/broker` 三个页面(broker-无关)

**只需新增:**

- `tradingbot/broker/webull.py` —— `WebullBroker(BrokerAdapter)`,用官方 SDK 映射账户/持仓/下单/状态,参照 `alpaca.py`,~200 行
- `tradingbot/broker/factory.py` 加 `webull` 分支
- 凭证处理:Trading API(App Key/Secret)或 Connect API(OAuth token)
- 字段映射 + Webull order status → 我们的 `OrderStatus`
- (可选)gRPC 订单回报 → 更新本地订单镜像;首版可用 `get_order` 轮询

## 实现设计

### `tradingbot/broker/webull.py`

```python
class WebullBroker(BrokerAdapter):
    def __init__(self, app_key, app_secret, account_id, *, region="us", paper=True):
        # 惰性 import webull SDK(同 alpaca.py 模式)
        ...
    def get_account(self) -> AccountInfo: ...        # Account Balance
    def get_positions(self) -> List[Position]: ...   # Account Positions
    def get_position(self, ticker): ...
    def get_latest_price(self, ticker) -> float: ... # Market Data HTTP / quote
    def submit_order(self, ticker, qty, side, order_type=MARKET, limit_price=None, time_in_force="day") -> Order: ...
    def get_order(self, order_id) -> Order: ...
    def cancel_order(self, order_id) -> bool: ...
    def get_order_history(self, limit=100) -> List[Order]: ...
```

字段映射要点(实施时按 SDK 实际字段核对):
- `AccountInfo`：account balance 的 cash / net liquidation / buying power / equity
- `Position`：symbol / qty / cost price / last price / market value / unrealized pnl
- 订单状态:Webull status → `OrderStatus`(Filled→FILLED,Cancelled→CANCELLED,Pending/Working→PENDING,PartiallyFilled→PARTIALLY_FILLED,Rejected→REJECTED)
- 下单不自动重试(避免重复单),与 IBKR 一致

### factory

`build_broker` 加分支:`webull` → `WebullBroker(app_key, app_secret, account_id, region, paper)`,凭证从 config / 桌面端本地配置读。

### 鉴权选择(与部署方向绑定)

- **桌面端模型(我们倾向的多用户方向)**:用户在桌面端填自己的 **Webull App Key/Secret**(或走 Connect API OAuth),**存桌面端本地(OS keychain)**,直接调 Webull 云端。**服务器不存券商密钥**,与 IBKR-本地-TWS 原则一致。Webull 甚至不需要用户装任何本地软件,只要凭证 + 网络。
- **服务端多租户(若改走这条)**:Connect API(OAuth2)由服务器保管各用户 token——会重新引入"服务器存券商密钥",仅在明确接受时采用。

## 分阶段

- **阶段 0**:申请 Webull OpenAPI(或先用测试环境共享账户);明确走 Trading API 还是 Connect API。
- **阶段 1**:`WebullBroker` 只读(account/positions/get_latest_price)+ factory 分支 + 单测(fake SDK)。
- **阶段 2**:下单(market/limit)+ 撤单 + 订单状态;接入 `trade_approvals`/`broker_orders` 审批执行链路(已存在,无改动)。
- **阶段 3**:(可选)gRPC 订单回报实时更新镜像;期权/组合单。

## 开放问题

- 走 **Trading API(自用 key/secret)** 还是 **Connect API(多用户 OAuth)**?——取决于最终是单账户自用还是多用户各自账户。
- 凭证存哪:桌面端本地(推荐)vs 服务器加密存储。
- `get_latest_price` 用 Market Data HTTP 还是行情订阅;美区行情权限。
- Webull SDK 的确切字段名/枚举(实施时对着 SDK README 核对)。

## 一句话

接 Webull = 新增一个 `WebullBroker(BrokerAdapter)`(像 Alpaca 一样直接调云端 SDK)+ factory 一个分支;风控/审批/审计/API/前端**全部复用**。是四个 broker 里最容易的。
