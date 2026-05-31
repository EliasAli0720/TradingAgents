# Webull 接入设计 ② —— 服务端云经纪 + Connect API 多租户

日期：2026-05-31
分支：`phase/9-broker-integration`(沿用)
状态：**设计待评审**。本文是 `2026-05-30-webull-integration-design.md`(调研存档)的**续篇与定稿**,把方向对齐到现已落地的架构(IBKR + Electron 双通道 + sidecar + 审批/快照/分析链路全部完成)。

## 0. 两个已拍板决策(2026-05-31)

1. **运行位置 = 服务端云经纪。** Webull 作为**服务端 broker**,服务器直连 Webull 云端 REST;不进本地 sidecar。浏览器端与桌面端都通过现有 `serverBrokerClient` 通道使用它。这正是 Electron 设计里 P5「服务端通道接云经纪、桌面端可切换」的落地。
2. **鉴权 = Connect API(多用户 OAuth 2.0)。** 平台为**每个用户**保管其各自授权的 Webull 账户 token。每用户一套 token,服务端加密落库。

> ⚠️ **与既有原则的偏离(必须明确接受):** IBKR/桌面线坚持「服务器不存券商密钥」。本方案的 Connect API 让**服务器加密保管每用户的 OAuth token**(不是 App Secret,是用户授权产生的 access/refresh token)。这是「服务端云经纪」路线的固有代价,已在决策中接受。降低风险的做法见 §6 安全。

## 1. 与 IBKR 路线的关键差异

| 维度 | IBKR(已实现) | Webull(本设计) |
|---|---|---|
| 传输 | 本地 socket(ib_async)/ Redis 连接器代理 | **云端 REST**,服务端直接 HTTPS |
| 连接器进程 / Redis | 需要(单 socket 独占) | **不需要**(无状态请求-响应) |
| 账户模型 | 单一平台账户(共享) | **每用户各自账户**(多租户) |
| 凭证位置 | 本地 TWS,服务器无密钥 | 服务器加密保管每用户 OAuth token |
| 通道 | 桌面 local(sidecar) | 服务端 server(浏览器+桌面共用) |
| 鉴权门禁 | sidecar 起✓/gateway✓/session✓ | OAuth 已授权✓ + token 未过期✓ |

**含义:** Webull 的 `mode="server"` **不复用** IBKR 的 Redis 连接器路径——它是一条更短的直连路径。`build_broker` 里 Webull 的 server 分支直接构造 `WebullBroker`,无需 `redis_client`。

## 2. 复用清单(绝大部分 0 改动)

**0 改动直接复用:**
- `tradingbot/broker/base.py` —— `BrokerAdapter` + 统一模型(`AccountInfo`/`Position`/`Order`/`OrderSide`/`OrderType`/`OrderStatus`)
- `tradingbot/risk/gate.py`(RiskGate)、`tradingbot/broker/signal_mapper.py`
- `tradingbot/services/*` —— `TradeProposalBuilder` / `TradeExecutionService`
- `tradingagents/api/broker_repository.py` + `trade_approvals` / `broker_orders` 表
- `tradingagents/api/portfolio_repository.py` + `portfolio_analytics.py` + `portfolio_snapshots` 表
  —— **已经是按 `(user_id, account_id, broker)` 三元组作用域**,天生支持多 broker / 多账户,无需改表。
- `web/src/api/broker.ts`、`web/src/api/brokerChannel.ts` 的 `serverChannel`、`/broker` 三页 —— broker 无关。

**需要新增:**
- `tradingbot/broker/webull.py` —— `WebullBroker(BrokerAdapter)`(~250 行,参照 `alpaca.py`)
- `tradingbot/broker/factory.py` —— `webull` 分支(server 直连,无 Redis)
- 每用户凭证:`models.py` 新增 `BrokerCredential` 表 + `broker_credentials` 加密读写
- OAuth 路由:`routers/broker_oauth.py`(authorize / callback / refresh / disconnect)
- 每用户 broker 选择 + 构造:`BrokerProvider`(按当前用户选 ibkr 连接器 or webull 直连)
- 前端:Webull「连接/授权」入口(OAuth 跳转)+ broker 选择器

## 3. `WebullBroker` 适配器

`tradingbot/broker/webull.py`,惰性 import SDK(同 `alpaca.py`/`ibkr_connection.py` 姿势,使顶层 import 不拖入可选依赖)。

```python
class WebullBroker(BrokerAdapter):
    """BrokerAdapter backed by Webull OpenAPI Connect API (cloud REST).

    Stateless per request: constructed with one user's OAuth access token +
    account_id, so every web process can build its own — no shared socket,
    no Redis connector (unlike the IBKR server path).
    """
    def __init__(self, access_token, account_id, *, region="us", paper=False,
                 endpoint=None, token_provider=None):
        # token_provider: callable -> fresh access_token (用于过期自动刷新)
        from webull.core.client import ApiClient            # 惰性
        from webull.trade.trade_client import TradeClient
        ...

    def get_account(self) -> AccountInfo: ...        # account balance
    def get_positions(self) -> List[Position]: ...   # account positions
    def get_position(self, ticker): ...
    def get_latest_price(self, ticker) -> float: ... # mdata quote
    def preview_order(self, ...) -> dict: ...        # ★ Webull 有 preview 端点(类 whatIf)
    def submit_order(self, ticker, qty, side, order_type=MARKET,
                     limit_price=None, time_in_force="day") -> Order: ...
    def get_order(self, order_id) -> Order: ...
    def cancel_order(self, order_id) -> bool: ...
    def get_order_history(self, limit=100) -> List[Order]: ...
    def health(self) -> dict: ...                    # token 有效?account?
```

**实现要点(已联网核实,2026-05):**
- SDK:`pip install webull-openapi-python-sdk`(Python 3.8–3.13;底层 `webull-python-sdk-core/-trade/-mdata/...`)。加入 `pyproject.toml` 可选依赖。
- 初始化(Trading 形态):`ApiClient(app_key, app_secret, "us")` → `TradeClient(api_client)`;**Connect 形态**是**双重鉴权**:`Authorization: Bearer <access_token>`(OAuth)**+** `app_key/app_secret` 做请求 HMAC 签名(注册时一并下发)。base URL prod `https://us-oauth-open-api.webull.com/oauth-openapi/`,UAT `https://us-oauth-open-api.uat.webullbroker.com/oauth-openapi/`。实现时对照 Connect API SDK 用法核对(SDK 可能已封装签名,只需注入 token + endpoint)。
- ⚠️ **下单用 `instrument_id` 而非 ticker。** 需一步「symbol → instrument_id」解析(类 IBKR `qualifyContracts`)。instrument 查询限速 **10/30s** → 必须 `{symbol: instrument_id}` 进程内缓存。
- 下单字段:`client_order_id`(幂等键,我们用 approval_id 或 uuid)/ `instrument_id` / `side` / `tif` / `order_type` / `limit_price` / `qty`。
- 订单状态映射 → 我们的 `OrderStatus`:Filled→FILLED、PartiallyFilled→PARTIALLY_FILLED、Cancelled→CANCELLED、Pending/Working/Submitted→PENDING、Rejected/Failed→REJECTED。
- **限速**:account 2/2s、place 600/60s、preview 150/10s、instrument 10/30s → 加客户端限流(简单 token bucket / 最小间隔)。
- **下单不自动重试**(避免重复单),靠 `client_order_id` 幂等;与 IBKR 一致。
- `time_in_force`:我们 `day/gtc/...` → Webull `DAY/GTC/...`。
- (后续)gRPC 订单回报实时回写镜像;**首版用 `get_order` 轮询**(执行后 `TradeExecutionService` 已写 pending 镜像,状态更新走 `POST /broker/orders/{id}/status` 或定时对账)。

## 4. 每用户凭证:`BrokerCredential`

新表(additive,`init_db()` 的 `create_all` 自动建,无 alembic):

```python
class BrokerCredential(Base):
    __tablename__ = "broker_credentials"
    id: int (pk)
    user_id: str (index, not null)
    broker: str = "webull"            # 预留多 broker
    account_id: str | None            # Webull 授权后回填主账户
    region: str = "us"
    access_token_enc: str             # Fernet 加密(复用 crypto.py)
    refresh_token_enc: str | None     # 可能为空(见 §6 兜底)
    token_expires_at: datetime | None # access_token 到期时刻(≈ now + 30min)
    refresh_expires_at: datetime | None  # refresh_token 到期(≈ now + 15d)
    scope: str | None
    status: str = "connected"         # connected | expired | revoked
    created_at / updated_at
    __table_args__ = (UniqueConstraint("user_id", "broker", "account_id"),)
```

- **加密复用** `tradingagents/api/crypto.py` 的 `encrypt_secret/decrypt_secret`(Fernet,key = 现有 env `MODEL_API_KEY_ENCRYPTION_KEY`;与 model API key 同一套),明文 token 不落库、不出日志、不回前端。
  - 注:env 名目前叫 `MODEL_API_KEY_*`,语义已扩展到"所有密钥加密";沿用即可,不必新增 env(避免再加运维项)。
- `BrokerCredentialRepository(session, user_id)`:`get(broker)` / `upsert(...)` / `mark_expired` / `revoke` / 解密取 token。

## 5. 服务端构造:`BrokerProvider`(按用户选 broker)

现状 `routers/broker.py:get_broker` 只会建「IBKR over Redis」的共享 broker。多 broker / 多租户后,broker 由**当前用户 + 其选定 broker**决定。新增一个 provider 依赖:

```python
def get_broker(user=Depends(get_current_user), session=..., config=..., redis=...):
    active = resolve_active_broker(user, session)   # 'ibkr' | 'webull'
    if active == "webull":
        cred = BrokerCredentialRepository(session, user.user_id).require("webull")
        token = ensure_fresh_token(cred, session)   # 过期则用 refresh_token 刷新并回写
        return WebullBroker(token, cred.account_id, region=cred.region,
                            token_provider=lambda: ensure_fresh_token(cred, session))
    # 默认 IBKR：维持现有 connector 路径(需要 redis)
    return BrokerConnectionService(config, redis).build_broker()
```

- `resolve_active_broker`:读用户级设置 `active_broker`(新增一个 user setting / 或 `BrokerCredential.status==connected` 推断)。**首版**可简单:有 Webull 连接就用 Webull,否则 IBKR。
- 关键收益:`/broker/account`、`/positions`、`/orders/preview`、审批 `build`/`execute` 等**全部端点零改动**——它们只调 `BrokerAdapter`,provider 透明换实现。
- `account_id` 作用域:审批执行写 `broker_orders.account_id` 时,IBKR 用 `config.ibkr_account_id`,Webull 用 `cred.account_id` → 由 provider 一并提供给 `execute_approved(account_id=...)`。

## 6. OAuth 流程与路由(新增 `routers/broker_oauth.py`)

平台先**邮件申请** Connect App(发 `connect.api@webull-us.com`,提供公司名 + redirect_uri),审核后下发 **`client_id` / `client_secret` / `scope` / `app_key` / `app_secret`**(前两个 + scope 用于 OAuth,后两个用于请求 HMAC 签名)。**不是后台自助申请。** 然后标准 OAuth 2.0 授权码流:

```
GET  /broker/oauth/webull/authorize
   → 生成 state(绑定 user_id,签名/存 redis,防 CSRF)
   → 302 到 Webull authorize URL(client_id, redirect_uri, scope, state)
[用户在 Webull 登录并授权]
GET  /broker/oauth/webull/callback?code=&state=
   → 校验 state → 用 code 换 access_token + refresh_token(+expires_in)
   → 拉 account_list 取主 account_id
   → BrokerCredentialRepository.upsert(加密落库)
   → 302 回前端 /broker?connected=webull
POST /broker/oauth/webull/refresh    (内部/定时)：refresh_token 换新 access_token
POST /broker/oauth/webull/disconnect ：revoke + 删/置 revoked
GET  /broker/oauth/webull/status     ：connected / expired / not_connected + account_id
```

**⚠️ token 生命周期(官方,核实于 2026-05)——决定刷新策略:**

| token | 有效期 | 取得方式 |
|---|---|---|
| authorization code | **60 秒**、一次性 | 用户浏览器授权回调 |
| **access_token** | **仅 30 分钟** | code 换 / refresh 换 |
| refresh_token | **15 天** | 随 access_token 一起返回;每次 refresh 同时换发新的 access+refresh(滚动) |

- **30 分钟极短** → 不能"登录一次长期用"。`ensure_fresh_token` 必须在**每次**构造 broker 前检查 `token_expires_at`,过期(或剩余 < ~2min)就用 refresh_token 换新并回写 `BrokerCredential`。因为是**滚动刷新**(每次 refresh 同时换新 refresh_token + 重置 15 天),只要用户 15 天内有活动就不必重新授权。
- 刷新失败 / refresh_token 过期(15 天未用)→ `status=expired`,前端提示重新走 authorize。
- ⚠️ **兜底**:有二手集成文档称 Webull 早期"未实装 refresh token"。实现时先验证 token 端点是否真返回 refresh_token;若没有,则 access_token 过期即要求重新授权(`status=expired`),`refresh_token_enc` 允许为空。
- **base URL / 端点**:prod `https://us-oauth-open-api.webull.com/oauth-openapi/`,UAT `https://us-oauth-open-api.uat.webullbroker.com/oauth-openapi/`。authorize/token 的确切 path(参考「Create And Refresh Token」「Create Access Token」端点)、scope 取值**实现时对照 Connect API authentication 文档核对**(本设计不锁死路径)。
- 权限:授权/断开 = 登录用户本人(写自己的 cred);读 status = 本人。

## 7. 鉴权门禁(对齐现有 `<BrokerGate>`)

现有 `BrokerGate` 对 server 通道是直通的(只有桌面 local 通道强制"连接先行")。Webull 引入「server 通道也需要先授权」:
- `brokerApi.status()`(`GET /broker/status`)对 Webull 用户返回 `connected = (cred.status==connected && token 未过期)`,`brokerage_session` 同义。
- 未连接 → broker 页展示「连接 Webull」按钮 → 跳 `/broker/oauth/webull/authorize`。
- `tradingEnabled = connected`;交易动作未授权前 disabled。
- 登录/分析永不门禁(不变)。

## 8. 前端改动(小、行为兼容)

- `web/src/api/broker.ts`:加 `oauthAuthorizeUrl()`(返回授权入口)、`disconnectWebull()`、broker 选择(若做多 broker 切换)。
- broker 选择器:`status.tsx` / Sidebar 的 broker pill 显示当前 broker(ibkr/webull)+ 连接态;Webull 未授权时给「连接 Webull」CTA。
- `serverChannel` 已能跑 status/account/positions/orders/refresh —— Webull 走它即可,**无需新通道**。
- 审批/执行:server 通道下 `approveProposal` 已是「服务端下单」路径(`tradeFlow.ts` 里 server 分支直接 `brokerApi.approve`)——Webull 自动适用,前端 0 改动。
- 浏览器端(非 Electron)现在**也能交易 Webull**(这是本路线相对桌面-local 的新增能力)。

## 9. 风控 / 记账 / 分析

- RiskGate 的 circuit-breaker 读服务端 `PortfolioDatabase`(SQLite)——Webull 真实组合在 Webull 云端;首版日内 PnL 风控会降级。改进:用 `portfolio_snapshots`(已有,按 user/account/broker)或实时账户算敞口。
- 净值快照:浏览器/桌面连接时仍可 `POST /broker/snapshot`(已有),Webull 用户 `broker="webull"` + `account_id=cred.account_id`,分析页/业绩页天然分割。
- ⚠️ **混币种**(见 `ibkr_integration` 的 HKD 坑):Webull 美区账户多为 USD,较简单;但仍按账户本位币处理,不要硬编码 USD。

## 10. 分阶段(开发顺序)

- **W0 准备**:注册 Webull Connect App(client_id/secret + redirect_uri);开通 UAT 共享测试账户。`pyproject.toml` 加 SDK 可选依赖。
- **W1 适配器 + 只读**:`WebullBroker`(account/positions/get_latest_price + instrument 解析缓存)+ factory `webull` 分支;单测用 **fake SDK**(不触网)。`build_broker(broker="webull", mode="server")` 通。
- **W2 凭证 + OAuth**:`BrokerCredential` 表 + repo(加密)+ `broker_oauth.py`(authorize/callback/refresh/disconnect/status)+ `BrokerProvider` 接进 `get_broker`。`/broker/status`/`/account`/`/positions` 对 Webull 用户跑通。
- **W3 交易**:`preview_order` / `submit_order`(client_order_id 幂等)/ `cancel_order` / `get_order`;接现有 `trade_approvals`/`broker_orders` 审批执行链路(**0 改动**);`get_order` 轮询回写状态。
- **W4 前端**:Webull 连接/断开入口 + broker pill/选择器 + 门禁;浏览器端交易打通。
- **W5(可选)**:gRPC 订单回报实时镜像;期权/组合单;多 broker 显式切换 UI。

## 11. 测试

- `tests/broker/test_webull.py`:fake SDK 驱动 `WebullBroker` 全方法(含 instrument 缓存、状态映射、限速、幂等)。
- `tests/api/test_broker_oauth.py`:authorize 重定向 + state 校验、callback 换 token(mock token 端点)、refresh、disconnect、加密落库往返、用户隔离。
- `tests/api/test_broker_provider.py`:同一组 `/broker/*` 端点在「IBKR 用户 / Webull 用户」下分别命中正确 broker;Webull 用户无 redis 也能跑。
- 复用现有 broker_repository / portfolio_analytics 测试(broker 无关)验证不回归。

## 12. 开放问题(实现前定)

- Connect API 的 authorize/token 确切 path + scope 取值(对照官方 auth 文档)。
- `redirect_uri` 用哪个域(线上 https 回调);桌面端 OAuth 回调如何落地(系统浏览器授权 → 回服务端 callback → 桌面轮询 status,**不**在 Electron 内嵌 webview 登录)。
- `active_broker` 怎么定:用户显式选 vs 自动(有 Webull cred 即用)。多 broker 并存时的切换 UX。
- 行情 `get_latest_price`:Webull mdata 行情权限 / 是否需额外订阅;美区行情层级。
- token 刷新调度:惰性(构造前检查)足够,还是加后台定时刷新避免首请求延迟。

## 13. 一句话

Webull 服务端云经纪 = 新增 `WebullBroker(BrokerAdapter)` 直连云端 + factory 一个 server 直连分支(无 Redis)+ 每用户 OAuth token 加密落库(`BrokerCredential`)+ 一个 `BrokerProvider` 按用户选 broker + 一组 OAuth 路由;**风控/审批/审计/分析/前端三页/快照链路全部复用**。相对桌面-local 路线,代价是「服务器保管每用户 token」与一套 OAuth 流程,收益是「浏览器端也能多用户各自交易」。
