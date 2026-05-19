# React/FastAPI Worker 前端分离设计

## 背景

`phase/5-frontend-refactor` 分支目前有两套 Python 前端：

- `cli/main.py` 中的 Rich/questionary CLI，用于配置并运行 TradingAgents 分析。
- `tradingbot/dashboard/` 中的 Streamlit dashboard，用于展示组合状态、收益表现、交易历史、Agent 推理、风险状态和手动快捷交易。

目标是做完整的前端分离：React 成为主用户界面，Python 继续负责 TradingAgents 分析、券商接入、风险检查、调度、持久化和报告生成。

## 目标

- 构建完整 React Web 应用，替代 CLI 分析界面和 Streamlit dashboard。
- 新增 FastAPI 后端，通过稳定的 HTTP 和实时 API 暴露现有 Python 功能。
- 长时间运行的 LLM 分析和交易任务必须通过 worker/队列执行，不能直接跑在请求处理线程里。
- 支持服务器或局域网单用户部署，并使用访问 token 做认证。
- Web UI 允许手动下单，也允许审批自动交易提案；交易操作必须二次确认并写入审计日志。
- API key 和券商密钥只保存在后端。前端可以显示所需 `.env` 变量是否已配置，但不能展示或存储密钥值。

## 非目标

- 多用户、角色权限、团队协作或按用户隔离组合。
- 第一轮实现中删除现有 CLI 或 Streamlit 代码。
- 允许未认证访问交易操作。
- 替换现有 TradingAgents、TradingBot、broker、risk 或 portfolio 领域逻辑。

## 架构

在同一个仓库内采用分离式 Web 架构：

- `apps/web/`：Vite + React + TypeScript 前端。
- Python FastAPI 包，例如 `tradingagents/api/`：REST API、认证、实时事件流、设置和 Web 侧编排。
- Worker 包，例如 `tradingagents/worker/` 或 `tradingbot/worker/`：队列消费者，执行长时间运行的分析和交易任务。
- 使用 Redis + RQ 作为队列层。
- 第一版继续使用 SQLite，扩展当前 TradingBot 数据库。
- Docker Compose 后续提供 `redis`、`api`、`worker`、`web` 四个服务。

FastAPI 请求处理器只负责入队长任务并返回 id。Worker 执行 `TradingAgentsGraph`、`AutoTrader`、broker、risk 和 portfolio 操作。所有任务生命周期变化都写入事件表，前端刷新页面或重连后可以恢复状态。

## 前端技术栈

使用：

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query 管理服务端状态
- 一个轻量事件 reducer 管理 run/event stream 状态
- 组合和收益图表使用兼容 Plotly 的方案，或在实现阶段选择合适的 React 图表库

视觉方向是专业的交易/分析工作台：信息密度高、便于扫读、偏操作型。需要保留当前 CLI 面板布局中有价值的部分，同时让 Streamlit dashboard 的工作流拥有一套更清晰的一等导航。

## 前端页面

应用使用左侧 sidebar 布局，导航项：

- `Workbench`
- `Runs`
- `Portfolio`
- `Performance`
- `Trades`
- `Risk`
- `Approvals`
- `Settings`

### Analysis Workbench

替代 CLI 流程。

能力：

- 配置 ticker、分析日期、输出语言、analysts、research depth、LLM provider、quick/deep models、provider 专属 thinking 设置、checkpoint 行为和资产类型。
- 校验 ticker/date，并在后端缺少对应 API key 时禁用相应 provider。
- 通过 API 创建分析 run。
- 展示实时状态：agent 进度、messages、tool calls、token/tool 统计、当前报告段落和最终报告。

### Runs / Reports

展示历史和当前分析任务。

能力：

- 按 ticker、日期、状态、provider 和 signal 筛选。
- 打开 run 详情页后展示 12-agent reasoning、最终 signal、报告分段、事件时间线和导出入口。
- 读取当前 TradingAgents 结果目录里已经存在的报告和 full-state logs。

### Portfolio

替代 Streamlit `portfolio_view`。

能力：

- 账户 KPI：equity、cash、invested value、buying power、unrealized P&L。
- 当前持仓表。
- 资产配置图。
- 可选手动交易入口。

### Performance

替代 Streamlit `performance_view`。

能力：

- Total return、realized P&L、Sharpe、max drawdown、win rate、total trades、avg win/loss、profit factor。
- Equity curve。
- Drawdown chart。
- Daily P&L chart。

### Trade History

替代 Streamlit `trades_view`。

能力：

- 交易表，支持按 ticker 和 side 筛选。
- Closed positions 表。
- 每笔交易关联的 agent reasoning；存在 full-state log 时直接读取。

### Risk Monitor

替代 Streamlit `risk_view`。

能力：

- Circuit breaker 状态。
- 总 exposure 与配置上限对比。
- Cash reserve 状态。
- 单仓 concentration 与单仓上限对比。
- 风险限制展示。

### Approvals

新增 human-in-the-loop 自动交易审批工作流。

能力：

- 列出 pending、approved、rejected、executed、failed 状态的交易提案。
- 展示 ticker、signal、拟议 side/quantity/value、risk verdict、模型推理和生成时间。
- 审批或拒绝提案。
- 审批必须二次确认，例如输入 `APPROVE {TICKER}`。
- approve/reject 都写入审计记录。

### Settings

能力：

- 展示后端环境状态：provider keys 是否配置、broker 类型、paper/live 模式、DB 路径、results 路径、watchlist、risk limits、scheduler times。
- 允许修改非密钥运行配置，例如 watchlist、risk limits、scheduler times。
- 永远不展示 API key 值。缺失密钥时只展示需要配置的 `.env` 变量名。

## 后端 API

所有受保护接口都需要访问 token 认证。

### Auth

- `POST /api/auth/login`：校验配置的访问 token，并发放 session。
- `GET /api/auth/me`：返回当前访问状态。

### Settings

- `GET /api/settings`：返回 provider、broker、risk、scheduler、watchlist 和 API key 配置状态。
- `PATCH /api/settings/runtime`：更新非密钥运行配置。

### Analysis Runs

- `POST /api/runs`：创建并入队一个分析 run。
- `GET /api/runs`：列出 runs。
- `GET /api/runs/{run_id}`：获取 run 详情。
- `GET /api/runs/{run_id}/events`：通过 SSE 推送 run events。
- `POST /api/runs/{run_id}/cancel`：请求取消 run。
- `GET /api/runs/{run_id}/report`：返回完整 Markdown/JSON 报告。

### Reports / Logs

- `GET /api/reports`：列出已经持久化的报告和 full-state logs。
- `GET /api/reports/{report_id}`：返回分段后的 12-agent 内容。
- `GET /api/reports/{report_id}/export?format=md|html|pdf`：导出报告。

### Portfolio

- `GET /api/portfolio/account`
- `GET /api/portfolio/positions`
- `GET /api/portfolio/snapshots`
- `GET /api/portfolio/performance`

### Trades

- `GET /api/trades`
- `GET /api/trades/{trade_id}`
- `POST /api/trades/manual`：提交手动交易，要求二次确认。
- `GET /api/trades/{trade_id}/reasoning`

### Risk

- `GET /api/risk/status`
- `GET /api/risk/limits`

### Approvals

- `GET /api/approvals`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`

### Bot / Scheduler

- `GET /api/bot/status`
- `POST /api/bot/run-watchlist`
- `POST /api/bot/start-scheduler`
- `POST /api/bot/stop-scheduler`
- `GET /api/bot/jobs`

## 实时事件模型

统一使用一个事件 envelope：

```json
{
  "event_id": "evt_...",
  "run_id": "run_...",
  "type": "agent_status | message | tool_call | report_section | stats | approval_required | completed | failed",
  "timestamp": "2026-05-19T12:00:00Z",
  "payload": {}
}
```

`GET /api/runs/{run_id}/events` 应先回放已持久化事件，再继续推送新事件。前端应尽量使用最后一个已收到的 event id 重连。

## Worker 和队列

第一版使用 Redis + RQ。

Worker 职责：

- 执行入队的 TradingAgents 分析 run。
- 执行 AutoTrader watchlist run。
- 执行 post-market portfolio snapshot。
- 需要人工审批时创建 approval record，而不是直接执行交易。
- 将已批准的交易提案作为队列任务执行。
- 写入 run events、状态变化、错误和审计记录。

第一版选择 RQ 而不是 Celery，因为它更简单，并且足够覆盖当前项目的初始任务模型。API 和 DB schema 仍应保留足够抽象，后续必要时可以替换队列实现。

## 持久化

扩展当前 SQLite portfolio 数据库。

保留已有表：

- `trades`
- `snapshots`
- `closed_positions`

新增：

- `analysis_runs`：id、ticker、分析日期、资产类型、provider/model 配置、状态、时间戳、错误摘要、结果引用。
- `run_events`：id、run id、event type、JSON payload、timestamp。
- `approvals`：id、关联 run/job/trade proposal、ticker、signal、side、quantity、预估 price/value、status、created/approved/rejected/executed 时间戳、reason。
- `audit_log`：id、action、actor/session id、target type/id、payload 摘要、timestamp、outcome。

Run 状态：

- `queued`
- `running`
- `waiting_approval`
- `completed`
- `failed`
- `cancel_requested`
- `cancelled`
- `stale`

## 取消机制

排队中的 job 可以在执行前取消。

运行中的 job 使用协作式取消：

- API 设置 `cancel_requested`。
- Worker 在安全边界检查取消状态，尤其是 graph chunk/node 之间。
- 当前 LLM/provider 请求不保证能立即停止。
- UI 应明确显示“取消请求已发送，会在当前步骤结束后生效”。

## 安全

部署场景是局域网/服务器单用户。

必须具备：

- 后端环境变量配置访问 token。
- 除 login/health 外所有 API routes 都受保护。
- 交易执行和审批 routes 需要二次确认。
- 后端永远不返回密钥值。
- Settings 只显示 API key 已配置/缺失状态。
- UI 必须突出显示 broker 模式：mock、paper 或 live。
- 所有交易、审批、scheduler 和 settings 变更都写入审计记录。

## 错误处理

- Provider/API key 缺失：拒绝创建 run，并明确返回缺失的 env var。
- LLM/data/broker/risk 错误：写入 `failed` 事件，包含可读摘要和原始错误类型/消息。
- Worker 崩溃：API 启动或维护任务应把过旧的 running jobs 标记为 `stale` 或 `failed`。
- SSE 断线：前端自动重连，并回放已持久化事件。
- 交易失败：写入审计记录，并在 Approvals/Trades 中展示失败状态。

## 测试策略

### 后端

- FastAPI route tests：settings、runs、portfolio、trades、approvals、auth。
- Worker tests：事件写入、失败任务、approval-required 任务、取消。
- DB tests：新增表、event append/replay、approval 生命周期、audit log 写入。
- Security tests：缺失/错误 token、二次确认失败、密钥脱敏。

### 前端

- Vitest 测试 API client、run event reducer 和状态映射。
- React Testing Library 测试 Workbench 表单、run detail、Approvals 和 Settings。
- Playwright smoke tests：登录、创建 mock run、观察事件更新、查看报告、审批 mock proposal。

### 集成

- Docker Compose smoke test：`redis`、`api`、`worker`、`web` 能正常启动。
- 使用 mock broker 的端到端路径，不依赖真实 LLM 或 Alpaca。
- 可选 live-provider tests，通过环境变量保护。

## 实现备注

- 初始迁移期间保留现有 CLI 和 Streamlit 代码。
- 只在必要时把 CLI 展示/状态逻辑提取成后端无关 helper；不要强迫 React 复用 terminal-only 抽象。
- 优先使用类型化后端响应 schema，保证前端契约稳定。
- 本地 UI 开发从 mock broker 和 fake analysis worker fixtures 开始。
- Docker Compose 等 API、worker、web 各自有可用 dev command 后再加入。
