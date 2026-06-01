# 00 功能地图

本文先从用户可见功能入手，再说明每个功能背后由哪些服务和数据结构支撑。

## 1. 多智能体投研分析

用户可以通过 CLI、Python API、Web 页面创建一次完整分析。分析对象支持：

- `stock`：股票，默认启用 market/social/news/fundamentals 四类 analyst。
- `crypto`：加密资产，不能启用 fundamentals analyst，接口层会拒绝这种组合。

Web 入口：

- `/analysis/new` 新建分析。
- `/analysis/:runId` 查看进度、取消、查看结果、生成交易建议。
- `/analysis` 目前主要是 admin 视角的 run 列表。

后端核心：

- `tradingagents/api/routers/runs.py`：分析 run 的 HTTP API。
- `tradingagents/worker/jobs.py`：Celery worker 的 run 执行包装。
- `tradingagents/graph/trading_graph.py`：TradingAgentsGraph 顶层编排。
- `tradingagents/graph/setup.py`：LangGraph 节点和边。

一次分析的核心产物：

- analyst reports：market、sentiment、news、fundamentals。
- research debate：bull researcher、bear researcher、research manager。
- trader plan：交易员把研究计划转成交易倾向。
- risk debate：aggressive、conservative、neutral 三方风险讨论。
- portfolio decision：组合经理给最终五档评级。
- Markdown reports、完整 state JSON、DB result、run events、可选翻译。

## 2. Web 多用户系统

当前 Web/API 系统提供登录、注册、角色和用户配置。

角色：

- `admin`：管理员，可以看跨用户 run 和用户列表。
- `operator`：可以创建分析、取消分析、交易预览、下单、审批。
- `viewer`：可以登录和查看授权范围内的数据，但不能操作交易或创建受限 run。

认证方式：

- 登录后服务端写 `tradingagents_session` HttpOnly cookie。
- 同时写 `tradingagents_csrf` 非 HttpOnly cookie。
- 前端对 `POST/PUT/PATCH/DELETE` 自动加 `X-CSRF-Token`。

相关文件：

- `tradingagents/api/routers/auth.py`
- `tradingagents/api/deps.py`
- `tradingagents/api/middleware.py`
- `web/src/api/client.ts`
- `web/src/hooks/useAuth.ts`

## 3. 用户模型设置

Web 用户必须先配置模型，才能创建分析 run 或生成推荐。

配置内容：

- `llm_provider`
- `deep_think_llm`
- `quick_think_llm`
- `backend_url`
- 可选用户自己的 provider API key

用户 API key 加密后存在数据库里；没有用户 key 时，运行时回退服务端环境变量里的 provider key。加密依赖 `MODEL_API_KEY_ENCRYPTION_KEY`。

相关文件：

- `tradingagents/api/routers/settings.py`
- `tradingagents/api/model_settings_repository.py`
- `tradingagents/api/model_catalog_repository.py`
- `tradingagents/api/crypto.py`
- `tradingagents/llm_clients/*`

## 4. 股票推荐

推荐功能是一个独立入口，但最终会转成普通分析 run。

用户流程：

1. 在 `/recommendations` 配置 watchlist。
2. 点击生成推荐，后端用 quick LLM 读取 watchlist 和近期分析上下文，返回最多 5 个候选。
3. 用户选择推荐项，点击分析。
4. 后端为每个推荐项创建普通 `analysis_runs` 记录，后续完全走 `/runs -> dispatcher -> worker -> graph`。

重要区别：

- 推荐批次存在 `recommendation_batches`。
- 推荐项存在 `recommendation_items`。
- 推荐项状态只描述推荐项自己的分析触发状态；真实 run 状态仍来自 `analysis_runs`。
- 没有 watchlist 时，生成推荐会走 broad-market/model-expansion 模式。

相关文件：

- `tradingagents/api/routers/recommendations.py`
- `tradingagents/api/recommendation_service.py`
- `tradingagents/api/recommendation_repository.py`
- `web/src/routes/recommendations/index.tsx`

## 5. 报告、翻译和进度

分析 run 在 worker 中执行时会持续写进度事件：

- `run_queued`
- `run_dispatching`
- `run_started`
- `run_progress`
- `run_succeeded`
- `run_failed`
- `run_cancelled`

前端详情页通过两种方式拿进度：

- 定时轮询 `GET /runs/{run_id}`。
- SSE `GET /runs/{run_id}/events`。

成功后，前端读取：

- `GET /runs/{run_id}/result`
- `GET /runs/{run_id}/artifacts`

翻译逻辑：

- 用户语言是 `en` 时不翻译。
- 非英文用户会在 analyst section 出现时异步翻译一部分。
- run 成功后再 backfill 没翻译完的 section。
- 前端结果页会轮询直到当前语言的每个非空 section 都有翻译。

相关文件：

- `tradingagents/worker/jobs.py`
- `tradingagents/api/repositories.py`
- `tradingagents/api/events.py`
- `tradingagents/api/serialization.py`
- `web/src/hooks/useRunEvents.ts`
- `web/src/routes/analysis/detail.tsx`

## 6. Broker 连接状态

系统支持三类 broker 使用方式：

| 路径 | 使用者 | 是否 per-user | 是否需要本机 TWS | 是否需要 Redis connector |
| --- | --- | --- | --- | --- |
| Webull server | 浏览器和桌面 | 是 | 否 | 否 |
| IBKR server | 浏览器和服务端 | 否，平台共享 | connector 所在机器需要 | 是 |
| IBKR desktop local | Electron 桌面 | 是，用户本机 | 是 | 否 |

服务端 broker 入口统一是 `/broker/*`。当前用户有 connected Webull credential 时，服务端自动选 Webull；否则走 IBKR server connector。

前端桌面环境还会多一个 local channel：Electron renderer 通过 IPC 找 main process，main process 再调用本机 sidecar。

相关文件：

- `tradingagents/api/routers/broker.py`
- `tradingagents/api/broker_provider.py`
- `tradingbot/broker/factory.py`
- `tradingbot/broker/webull.py`
- `tradingbot/broker/ibkr.py`
- `tradingbot/broker/ibkr_connector.py`
- `tradingbot/sidecar/app.py`
- `web/src/api/brokerChannel.ts`

## 7. Webull 接入

Webull 当前支持两种凭据模式：

1. OAuth：平台有 `WEBULL_APP_KEY/SECRET` 或 OAuth client 配置，用户跳转授权，服务端保存 access/refresh token。
2. API key：用户直接在页面输入自己的 `app_key/app_secret`，服务端校验能列账户后加密保存。

API key 模式下，如果 Webull 返回多个账户，用户必须填 `account_id`；如果只有一个账户，系统自动选择。

Webull credential 存在 `broker_credentials`，唯一键是 `(user_id, broker)`。也就是说当前设计是每个用户一个 Webull active credential。如果要支持同一个用户同时绑定多个 Webull 账户，需要改表约束和 active account 选择逻辑。

相关文件：

- `tradingagents/api/routers/broker_oauth.py`
- `tradingagents/api/broker_credential_repository.py`
- `tradingagents/api/broker_provider.py`
- `tradingbot/broker/webull_client.py`
- `web/src/components/broker/WebullConnectCard.tsx`

## 8. 交易建议和人工审批

分析成功后，只有最终 `decision` 是 `BUY / OVERWEIGHT / UNDERWEIGHT / SELL` 时，前端才允许生成交易建议。`HOLD` 会显示无需交易。

生成建议时：

1. 读取 run 和 result。
2. 根据 signal 用 `SignalMapper` 计算买卖方向和仓位比例。
3. 从当前 broker 读最新价格、账户、持仓。
4. 做第一道 RiskGate。
5. 写入 `trade_approvals`，状态为 `pending`。

批准时：

1. `pending -> approved`。
2. 重新读最新价格。
3. 第二道 RiskGate。
4. best-effort preview margin。
5. 真正 submit order。
6. 写入 `broker_orders` mirror。
7. approval 标记为 `submitted` 或 `failed`。

相关文件：

- `tradingbot/services/trade_proposal.py`
- `tradingbot/services/trade_execution.py`
- `tradingbot/broker/signal_mapper.py`
- `tradingbot/risk/gate.py`
- `tradingagents/api/broker_repository.py`
- `web/src/api/tradeFlow.ts`

## 9. 手动快速下单

手动快速下单在 `QuickTrade` 组件里，目标是绕开分析建议，直接让 operator/admin 发一笔订单。

路由选择：

- 如果 server status 是可用的 Webull，直接走服务端 `/broker/orders/preview` 和 `/broker/orders`。
- 如果是 Electron 桌面且本地 IBKR sidecar 可用，预览和下单走 sidecar，下单结果再回写 `/broker/orders/manual`。
- 如果两者都不可用，按钮禁用并提示先连接账户。

相关文件：

- `web/src/components/broker/QuickTrade.tsx`
- `web/src/api/manualTradeFlow.ts`
- `tradingagents/api/routers/broker.py`

## 10. 组合、业绩、交易历史和风险页面

当前 Web 页面的组合类功能分两类数据来源：

- 实时账户和持仓：通过当前 broker channel 读取 `account/positions`。
- 业绩和交易历史：读服务端 DB mirror，即 `broker_orders` 和 `portfolio_snapshots`。

桌面端会定期把账户快照推到 `/broker/snapshot`，服务端按 `(user_id, account_id, broker, date)` upsert。

相关文件：

- `tradingagents/api/portfolio_repository.py`
- `tradingagents/api/portfolio_analytics.py`
- `web/src/hooks/useSnapshotPush.ts`
- `web/src/routes/placeholder/portfolio.tsx`
- `web/src/routes/placeholder/performance.tsx`
- `web/src/routes/placeholder/trades.tsx`
- `web/src/routes/placeholder/risk.tsx`

## 11. 自动交易机器人和 Streamlit 旧入口

仓库仍保留 `tradingbot/` 的机器人和 Streamlit dashboard。这套功能比 Web/API 更早，主要入口：

- `run_bot.py`
- `run_dashboard.py`
- `run_auth.py`

机器人链路：

```text
TradingAgentsGraph.propagate()
  -> SignalMapper
  -> RiskGate
  -> BrokerAdapter
  -> PortfolioManager / SQLite
```

它和 Web/API 共享部分 broker、risk、portfolio 代码，但存储上还有本地 SQLite：

- `~/.tradingagents/tradingbot.db`
- `~/.tradingagents/users.db`

因此排查 Web 页面时不要把 Streamlit 本地 SQLite 和 Web API PostgreSQL 混为一个数据源。
