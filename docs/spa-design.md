# TradingAgents SPA 设计方案

## 1. 目标与范围

新建一个独立的 Web 前端（SPA），通过 `tradingagents/api`（FastAPI，下文简称「API」）完成 Streamlit 仪表盘当前提供的全部功能，并把分析、管理、设置统一到一个 UI 里。

最终前后端关系：

```
Browser (SPA) ──HTTP+Cookie──▶ FastAPI(:8000) ──▶ PostgreSQL / Redis / Celery worker / TradingAgentsGraph
                                                ──▶ tradingbot (broker / portfolio / risk)  ← 需要新增 API 暴露
```

Streamlit 仪表盘短期内**保留**，作为离线/本地兜底；SPA 上线并稳定后再决定是否下线。

---

## 2. 功能盘点：Streamlit 现状 → SPA 页面映射

> ✅ = API 已存在；🟡 = 需要在 FastAPI 中**新增端点**才能搬过来。

| Streamlit 模块 | SPA 路由 | 主要内容 | API 依赖 |
|---|---|---|---|
| `/login`（登录/注册卡片） | `/login` | 登录、注册、错误提示、429 限速提示 | ✅ `POST /auth/login`、`POST /auth/register` |
| 侧边栏：登录态、语言、模式徽标、Watchlist、刷新、Logout | 顶栏 + 侧栏 + UserMenu | 全局壳 | ✅ `GET /auth/me`、`POST /auth/logout`；🟡 `GET /config`（mode/broker/watchlist） |
| `nav.signals`（Live Analysis + Historical Logs） | `/analysis` 列表 + `/analysis/new` + `/analysis/:runId` | 触发分析、SSE 实时进度、多 Agent Tabs、历史报告浏览 | ✅ `POST /runs`、`GET /runs/{id}`、`GET /runs/{id}/result`、`GET /runs/{id}/events`(SSE)、`POST /runs/{id}/cancel`、`GET /admin/runs`（自己视角需要补 `GET /runs`） |
| `nav.portfolio`（持仓、Allocation 饼图） | `/portfolio` | 当前持仓、市值、分配占比 | 🟡 `GET /portfolio/positions`、`GET /portfolio/allocation` |
| `nav.performance`（净值/回撤/日 PnL） | `/performance` | 三段图表 + KPI | 🟡 `GET /performance/equity`、`/drawdown`、`/daily-pnl` |
| `nav.trades`（成交流水、单笔详情、已平仓） | `/trades`、`/trades/:tradeId` | 流水表 + 详情 + 已平仓盈亏 | 🟡 `GET /trades`、`GET /trades/{id}`、`GET /trades/closed` |
| `nav.risk`（敞口、限额、规则） | `/risk` | 敞口指标 + 风控配置只读 | 🟡 `GET /risk/exposure`、`GET /risk/config` |
| 侧栏 Quick Trade | 全局右侧 Drawer | 手动下单、调用 broker | 🟡 `POST /orders`（含 ticker/side/qty/type） |
| 模型 Provider / Key 管理（当前 Streamlit 缺，是新需求） | `/settings/model` | 配置 LLM、保存 / 清空 key、validate | ✅ `GET/PUT/DELETE /settings/model`、`POST /settings/model/validate` |
| 账户：改密 | `/settings/account` | 修改密码 | ✅ `POST /auth/change-password` |
| 管理员：用户管理 | `/admin/users` | 列表、改角色/停用、撤销所有会话 | ✅ `GET /admin/users`、`PATCH /admin/users/{id}`、`POST /admin/users/{id}/sessions:revoke-all` |
| 管理员：所有分析任务 | `/admin/runs` | 列表 + 过滤（user_id、status） | ✅ `GET /admin/runs` |

### 需要在 FastAPI 中新增的接口清单（搬迁前置）

> 这些都是从 `tradingbot/dashboard/components/*.py` 现有逻辑「服务化」出来；建议放在新 router 文件下。

```
tradingagents/api/routers/portfolio.py   GET /portfolio/positions, /portfolio/allocation
tradingagents/api/routers/performance.py GET /performance/equity, /drawdown, /daily-pnl
tradingagents/api/routers/trades.py      GET /trades, /trades/{id}, /trades/closed
tradingagents/api/routers/risk.py        GET /risk/exposure, /risk/config
tradingagents/api/routers/orders.py      POST /orders   (Quick Trade)
tradingagents/api/routers/runs.py        GET /runs      (当前用户自己的任务列表，admin 走 /admin/runs)
tradingagents/api/routers/config.py      GET /config    (broker mode / paper / watchlist 等只读运行时配置)
```

权限：
- `GET` 类只读：登录即可。
- `POST /orders`：`admin` / `operator`，需 CSRF。
- `GET /admin/*`：仅 `admin`。

---

## 3. 技术选型

| 关注点 | 选型 | 理由 |
|---|---|---|
| 框架 | **React 18 + TypeScript + Vite** | 团队主流；冷启动快；HMR 体验好 |
| 路由 | **React Router v6** | 文件级嵌套路由、loader/action 支持 |
| 状态：服务端 | **TanStack Query v5** | 自动缓存、轮询、SSE 配套钩子简单 |
| 状态：UI | **Zustand**（轻量全局） | 模式徽标、Drawer 开关、i18n 切换 |
| UI 组件 | **shadcn/ui + Tailwind CSS** | 已有 `shadcn-ui` skill；与 dark 主题契合 |
| 图表 | **Recharts** | Equity / Drawdown / Allocation 都能覆盖 |
| 表单 + 校验 | **react-hook-form + zod** | 登录、创建分析、模型配置都是表单密集 |
| 国际化 | **i18next + react-i18next** | 复用现有 `tradingbot/dashboard/i18n.py` 的 key 体系 |
| HTTP | **axios**（实例 + 拦截器） | 易于注入 CSRF、统一错误处理；fetch 也行 |
| 实时 | **原生 EventSource**（封装为 `useRunEvents` hook） | 直接消费 `GET /runs/{id}/events` |
| 包管理 | **pnpm** | 工作区干净 |
| 代码质量 | ESLint + Prettier + tsc 严格模式 | 标准 |
| 测试 | Vitest + Testing Library + Playwright（关键路径 e2e） | 与 Vite 一体 |

---

## 4. 目录结构

```
web/                                ← 仓库根新目录，独立部署
├─ index.html
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
├─ tailwind.config.ts
├─ .env.example                     VITE_API_BASE=http://127.0.0.1:8000
└─ src/
   ├─ main.tsx                      QueryClientProvider, RouterProvider, I18nProvider
   ├─ App.tsx                       根布局壳：AuthGate + AppLayout
   ├─ routes/
   │  ├─ index.tsx                  /            重定向到 /analysis 或 /login
   │  ├─ login.tsx                  /login
   │  ├─ analysis/
   │  │   ├─ list.tsx               /analysis
   │  │   ├─ new.tsx                /analysis/new
   │  │   └─ detail.tsx             /analysis/:runId
   │  ├─ portfolio.tsx              /portfolio        (Phase 2)
   │  ├─ performance.tsx            /performance      (Phase 2)
   │  ├─ trades/
   │  │   ├─ list.tsx               /trades           (Phase 2)
   │  │   └─ detail.tsx             /trades/:tradeId
   │  ├─ risk.tsx                   /risk             (Phase 2)
   │  ├─ settings/
   │  │   ├─ model.tsx              /settings/model
   │  │   └─ account.tsx            /settings/account
   │  └─ admin/
   │      ├─ users.tsx              /admin/users
   │      └─ runs.tsx               /admin/runs
   ├─ api/
   │  ├─ client.ts                  axios 实例 + 拦截器（CSRF / 401 / 错误归一）
   │  ├─ auth.ts                    login/register/logout/me/changePassword
   │  ├─ settings.ts                model settings + validate
   │  ├─ runs.ts                    createRun, getRun, getResult, cancelRun, listRuns
   │  ├─ admin.ts                   admin endpoints
   │  ├─ portfolio.ts               Phase 2
   │  ├─ trades.ts                  Phase 2
   │  ├─ risk.ts                    Phase 2
   │  └─ orders.ts                  Phase 2 quick trade
   ├─ hooks/
   │  ├─ useAuth.ts                 当前用户 + role helpers
   │  ├─ useRunEvents.ts            EventSource + 自动重连 + 终止事件检测
   │  └─ useCsrf.ts                 从 cookie 读取 tradingagents_csrf
   ├─ components/
   │  ├─ layout/
   │  │   ├─ AppLayout.tsx          顶栏 + 侧栏 + Outlet + QuickTradeDrawer
   │  │   ├─ TopBar.tsx             logo / 模式徽标 / 语言 / UserMenu
   │  │   ├─ SideNav.tsx            带角色过滤的菜单
   │  │   └─ QuickTradeDrawer.tsx
   │  ├─ run/
   │  │   ├─ RunStatusBadge.tsx
   │  │   ├─ RunEventsStream.tsx    使用 useRunEvents
   │  │   ├─ AgentReportTabs.tsx    Market / Social / News / Fundamentals / Researchers …
   │  │   └─ DecisionCard.tsx
   │  ├─ charts/
   │  │   ├─ EquityChart.tsx
   │  │   ├─ DrawdownChart.tsx
   │  │   ├─ DailyPnlChart.tsx
   │  │   └─ AllocationPie.tsx
   │  └─ ui/                        shadcn 生成（button, dialog, table, …）
   ├─ stores/
   │  └─ uiStore.ts                 sidebarCollapsed / quickTradeOpen / language
   ├─ i18n/
   │  ├─ index.ts
   │  ├─ zh.json                    从 tradingbot/dashboard/i18n.py 翻译过来的 key
   │  └─ en.json
   └─ lib/
      ├─ format.ts                  数字 / 货币 / 时间
      └─ guards.ts                  RequireAuth, RequireRole
```

---

## 5. 关键交互机制

### 5.1 鉴权与 CSRF

- 登录后 API 写两个 cookie：`tradingagents_session`（HttpOnly）+ `tradingagents_csrf`（JS 可读）。
- SPA **不存储 token、不解析 session cookie**。
- axios 实例：
  - `withCredentials: true`
  - 请求拦截器：方法 ∈ {POST,PUT,PATCH,DELETE} 时，读 `tradingagents_csrf` 写入 `X-CSRF-Token`。
  - 响应拦截器：401 → 清 useAuth 状态 + redirect `/login?next=...`；403 弹 toast；429 显示倒计时。
- 路由守卫：
  - `RequireAuth`：未登录跳 `/login`，登录态从 `GET /auth/me`（首次加载阻塞一次）。
  - `RequireRole(['admin'])` / `RequireRole(['admin','operator'])`：包裹 admin 与写操作路由。

### 5.2 SSE：分析进度

```ts
// hooks/useRunEvents.ts
const es = new EventSource(`${BASE}/runs/${runId}/events`, { withCredentials: true });
es.addEventListener('run_started', ...);
es.addEventListener('agent_step', ...);
es.addEventListener('run_succeeded' | 'run_failed' | 'run_cancelled', () => es.close());
```

- 进入详情页 → 订阅；离开 → close。
- 终止事件触发 TanStack Query 失效 `['run', runId]` 和 `['runResult', runId]`，自动重拉。
- 失败重连：EventSource 原生重连即可；超过 N 次给用户「重试」按钮。

### 5.3 国际化

- 复用现有 i18n key 命名（`auth.*`、`app.*`、`nav.*`、`sig.*`、`pv.*`、`perf.*`、`tv.*`、`risk.*`、`qt.*`）。
- 一次性脚本 `scripts/extract_i18n.py`：把 `tradingbot/dashboard/i18n.py` 的 dict 导出成 `zh.json` / `en.json` 种子。
- 顶栏切换语言写入 `localStorage`，初始化时同步给 i18next。

### 5.4 跨域 / 部署

- 开发期：Vite proxy `/api → http://127.0.0.1:8000`，SPA 与 API 看起来同源，免 CORS。
- 生产：两种方案二选一
  - **同域反代**（推荐）：Nginx/Caddy 把 `/` 指 SPA 构建产物，把 `/api/*` 反代到 uvicorn；cookie 同域，CSRF 直通。
  - **独立域**：API 开 `CORSMiddleware`，`allow_origins=[SPA_ORIGIN]`、`allow_credentials=True`；cookie 需 `SameSite=None; Secure`。需要 API 侧配套改动。

### 5.5 错误与状态语义

| HTTP | UI 表现 |
|---|---|
| 401 | 重定向 `/login?next=...`，全局只触发一次 toast |
| 403 | inline 警告 + 隐藏受限操作按钮 |
| 404 (run) | 详情页：「任务不存在或无权访问」空状态 |
| 409 (cancel/result) | 按钮禁用 + 解释文案（已完成 / 未完成） |
| 422 | 表单字段级错误（zod schema 对齐后端约束） |
| 429 | 倒计时按钮（登录 / 重发） |
| 503 | toast「任务投递失败，请稍后再试」 |

---

## 6. 关键页面线框

### 6.1 `/analysis/new`（创建分析）

```
┌ New Analysis ─────────────────────────────────────┐
│ Ticker      [ AAPL          ]   (auto-upper)      │
│ Trade Date  [ 2026-05-27 ▼ ]                       │
│ Asset Type  ( ) Stock   ( ) Crypto                 │
│ Analysts    [✓] Market [✓] Social [✓] News         │
│             [✓] Fundamentals (disabled if crypto)  │
│                                                    │
│  Model: openai / gpt-4.1   (来自 /settings/model)   │
│  [ Validate Key ]  ← POST /settings/model/validate │
│                                                    │
│        [ Cancel ]            [ Create Run ▶ ]      │
└────────────────────────────────────────────────────┘
```

- 提交成功 → `navigate('/analysis/' + runId)`。
- 409 model not configured → 弹引导对话框「先去 /settings/model 配置」。

### 6.2 `/analysis/:runId`（详情 + SSE）

```
┌ AAPL  · 2026-05-27 ────────────────────────  [● running] [Cancel] ┐
│  Created 2026-05-27 22:00:57   Step: market analyst                │
│                                                                    │
│  ┌── Live events (SSE) ────────────────────────────────────┐       │
│  │  22:00:57  run_queued                                   │       │
│  │  22:00:57  run_started                                   │       │
│  │  22:01:03  agent_step  market                            │       │
│  │  …                                                       │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                    │
│  ┌── Decision ───────────────────────────────────┐                 │
│  │  (succeeded 后展示 BUY/HOLD/SELL + 摘要)        │                 │
│  └────────────────────────────────────────────────┘                 │
│                                                                    │
│  [Market] [Social] [News] [Fundamentals] [Researchers] [Trader] [Risk] [PM] │
│  ─────────────────────────────────────────────────────────────────  │
│  <Markdown 渲染对应 report>                                          │
└────────────────────────────────────────────────────────────────────┘
```

### 6.3 `/settings/model`

- 表单字段对应 PUT 端点；密码框风格隐藏 api_key；右侧显示 `has_api_key` + masked。
- 顶部按钮：`Validate` / `Clear API Key`（DELETE）。
- 提交后弹 toast，invalidate `['settings','model']`。

### 6.4 `/admin/users`

- 表格列：username / role / is_active / 操作。
- 行内编辑：role 下拉（admin/operator/viewer），is_active 切换 → PATCH。
- 右侧菜单：`Revoke all sessions`（确认对话框 → POST `…/sessions:revoke-all`）。

### 6.5 `/admin/runs`

- 顶部过滤条：user_id（下拉，来自 `/admin/users`）+ status（多选）。
- 表格：ticker / date / status / created_at / finished_at / 跳转详情。

### 6.6 全局 Quick Trade Drawer（Phase 2）

- 顶栏一个按钮 → 右侧 Drawer 滑出，ticker/side/qty 表单 → POST `/orders`。
- 仅 `admin` / `operator` 可见。

---

## 7. 分阶段实施（建议）

| 阶段 | 范围 | 依赖 | 价值 |
|---|---|---|---|
| **Phase 0**（脚手架） | Vite + React + TS + Tailwind + shadcn 初始化；axios + CSRF + i18n；AppLayout + Login | 现有 API | 1 周内有可登录的空壳 |
| **Phase 1**（分析闭环） | `/analysis` 列表/新建/详情/SSE/取消、`/settings/model`、`/settings/account` | ✅ 全部现成；需补 `GET /runs`（当前用户视角） | SPA 替代 Streamlit 的「Signals」与新功能「模型管理」 |
| **Phase 2**（Admin） | `/admin/users`、`/admin/runs` | ✅ 全部现成 | 运营/管理员侧 |
| **Phase 3**（交易侧搬迁） | `/portfolio`、`/performance`、`/trades`、`/risk`、Quick Trade | 🟡 需先在 API 增 `portfolio/performance/trades/risk/orders/config` 路由 | 关掉 Streamlit 的前置条件 |
| **Phase 4**（收尾） | E2E（Playwright）、可观测（Sentry/前端埋点）、CI 构建产物、Nginx 反代部署 | — | 上线就绪 |

> Phase 1 + 2 完成后，SPA 已经覆盖了 FastAPI 现有的全部能力。Phase 3 才是「真正替代 Streamlit」的关键，所以**API 扩展是阻塞项**，建议与 SPA Phase 0~2 并行启动。

---

## 8. 风险与开放问题

1. **cookie 跨域**：若 SPA 与 API 不同域，必须改 `Set-Cookie` 为 `SameSite=None; Secure`，否则浏览器不会带；推荐同域反代规避。
2. **CSRF cookie 必须 JS 可读**：当前 `tradingagents_csrf` 已是非 HttpOnly，SPA 才能取到；要保持这个约定。
3. **SSE 中转**：若部署在 Nginx 后，必须关 `proxy_buffering` 才能逐事件下发。
4. **多 worker 进度可见性**：当前 SSE 是回放 DB 事件 + 轮询；高并发场景下需评估是否引入 Redis pub/sub，对前端透明。
5. **Streamlit 与 SPA 并行期**：模型配置已经在 API 侧；Streamlit 侧的本地 user db 与 API 侧的 PG users 表是两套账号体系——并行期需评估是否做账号迁移脚本，或显式宣告「分析走 SPA、交易走 Streamlit」。
6. **i18n 字典对齐**：现有 Streamlit i18n 是 Python dict；要保证 SPA 与 Streamlit 在并行期的文案一致，建议用脚本从 Python 抽取 JSON，单一来源。
7. **Quick Trade**：Streamlit 现在直接调 `broker.submit_order`，搬到 API 后涉及凭据管理（Alpaca key 放服务端 env vs 用户级），需要在 Phase 3 之前先确定模型。

---

## 9. 立即可启动的两件事

1. **新建 `web/`** 跑 Phase 0：可登录、可看 `/auth/me`、Layout 壳搭好。
2. **在 FastAPI 立 issue/分支**：补 `GET /runs`（当前用户视角），这是 Phase 1 的唯一阻塞；其他 portfolio/performance/trades/risk 端点排到 Phase 3 前置。

