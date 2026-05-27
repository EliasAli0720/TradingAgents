# 服务化、SPA 上线与模型接入加固

日期：2026-05-27 ~ 2026-05-28
覆盖时间窗：2026-05-27 19:00 起至 2026-05-28 当前
分支：`phase/7-service-engineering`

依赖前置：
- `2026-05-26-analysis-http-api-design.md`（v1 HTTP API）
- `2026-05-26-analysis-api-auth-multitenancy.md`（cookie 鉴权 + 多租户）
- `2026-05-27-user-model-settings-design.md`（用户模型配置 + 加密 API key）

## 目标

把 phase/7 的服务化推进到"前端 SPA 接管 Streamlit 大部分能力"的里程碑，并修掉这一过程中暴露出的 MiniMax 中国站接入问题、目录数据流缺陷。整体 7 个提交 + 一次未提交的加固，按时间顺序分为六块：

1. **后端**：把 LLM provider / 模型下拉数据从 Python 硬编码搬进 DB，新增 `GET /settings/model/options`。
2. **前端**：从零搭一套独立 SPA（`web/`），替代 Streamlit 仪表盘的分析侧能力。
3. **前端 v2**：把模型设置改成"按后端 options 受控下拉"，分析结果加 DecisionCard + Markdown Tab 渲染。
4. **Worker**：分析任务运行完自动写入 Markdown 报告文件树，并把 `reports/` 加进 `.gitignore`。
5. **接入加固**：MiniMax `reasoning_split` 走 `extra_body`、minimax-cn 端点回退 `/v1` + 反向迁移、CN 模型目录与官方对齐。
6. **目录数据流**：`ensure_seeded()` 始终全量重建 model_options，补齐 openai/google/anthropic 的 `default_backend_url`。

## 非目标

- 不实现 Anthropic 兼容端点客户端（中国站当前 4 个模型由 OpenAI 兼容路径满足）。
- 不重写 LLM 客户端继承结构；仅最小补丁面。
- 不为已经把无效模型 ID 落到 `user_model_settings` 的历史用户做自动重写；保留状态，由用户在 SPA 上下次保存时显式重选。
- 不处理 MiniMax Token Plan / Highspeed 订阅状态（账号侧问题）；接入侧只负责把"不在官方支持列表的模型"从下拉里移除。
- 不实装真实的交易接口（Quick Trade / Portfolio / Performance / Trades / Risk）；SPA 给出 placeholder 页面 + Phase 3 后端补完信号。

---

## 块 1：DB-backed 模型目录后端化

**提交**：`9779f0b feat: add db-backed model options`、`9bae112 docs: document model options endpoint`

### 动机

第一版用户模型配置（5/27 上午落地）只把"已保存的模型"存了 PG，但下拉里"可选哪些 provider / 哪些模型"仍写死在 Python `MODEL_OPTIONS`。前端要做受控下拉就必须能用接口拿到这份元数据。

### 新增表

- `llm_provider_options`：provider 元数据（label / required_env_var / default_backend_url / backend_url_editable / supports_custom_model / sort_order）。
- `llm_model_options`：每个 provider 的 quick / deep 模型列表（唯一约束 `(provider_id, mode, model_id)`）。

启动时 `init_db()` 创建表；首请求触发 `ensure_seeded()` 把 Python `MODEL_OPTIONS` 灌入。

### 新增端点

`GET /settings/model/options`（需登录），返回：

```json
{
  "providers": [
    {
      "id": "openai",
      "label": "OpenAI",
      "required_env_var": "OPENAI_API_KEY",
      "default_backend_url": "https://api.openai.com/v1",
      "backend_url_editable": false,
      "supports_custom_model": false,
      "quick_models": [{"id": "gpt-5.4-mini", "label": "..."}, ...],
      "deep_models":  [{"id": "gpt-5.5",      "label": "..."}, ...]
    },
    ...
  ]
}
```

新文件：`tradingagents/api/model_catalog_repository.py`（156 行）+ Pydantic schemas + 路由 handler + `tests/api/test_model_settings_routes.py` + `tests/api/test_model_catalog_repository.py`。

---

## 块 2：SPA 从零搭起

**提交**：`581303a feat: spa web`（+58 行 / -58 行 -> 净 +4435 行）

### 技术栈

React 18 + TypeScript + Vite 5 + Tailwind 3 + TanStack Query v5 + React Router v6 + axios + react-hook-form + Zod + zustand。所有源码集中在 `web/`，与 Python 后端解耦。

### 关键工程决策

- **同源代理**：`vite.config.ts` 把 `/api/*` 反代到 `http://127.0.0.1:8000`，开发期免 CORS；生产由反代层负责。
- **CSRF 自动注入**：`src/api/client.ts` 的 axios 拦截器读 `tradingagents_csrf` cookie，写到 `X-CSRF-Token` 头；401 全局重定向 `/login?next=`。
- **`tsc --noEmit`**：早期手抖跑了 `tsc -b` 把 `.js` 编译产物落到了源码目录里——已修：`tsconfig.json` 加 `noEmit: true`，`package.json` `build` 改成 `tsc --noEmit && vite build`。
- **后端路径默认从 cookie 推导**：登录态由 `useAuth()` hook 通过 `GET /auth/me` 反向解析，无需在 SPA 显式存 token。

### 页面结构

| 路由 | 说明 | 后端依赖 |
|---|---|---|
| `/login` | 登录 / 注册（首位用户自动 admin） | `POST /auth/{login,register}` |
| `/analysis` | 任务列表（管理员看全量，operator/viewer 看注意提示） | `GET /admin/runs`（用户视角列表待 Phase 3 补 `GET /runs`） |
| `/analysis/new` | 创建分析任务表单（crypto 时禁用 fundamentals） | `POST /runs` |
| `/analysis/:runId` | 任务详情（状态 + SSE 实时事件 + 结果） | `GET /runs/{id}{,/result,/events}`、`POST /runs/{id}/cancel` |
| `/settings/model` | 模型配置 + 校验 + 清空 key | `GET/PUT/DELETE /settings/model*`、`POST /settings/model/validate` |
| `/settings/account` | 改密 | `POST /auth/change-password` |
| `/admin/users` | 用户管理（角色 / 启停 / 撤销会话） | `GET/PATCH /admin/users*` |
| `/admin/runs` | 全任务过滤 | `GET /admin/runs` |
| `/portfolio /performance /trades /risk` | Phase 3 占位（KPI 骨架 + Info 提示） | 待后端补 |

### Streamlit 1:1 视觉对齐

按 `docs/ui-guidelines.md` 的语义色卡（success `#4CAF50` / danger `#F44336` / info `#2196F3` / neutral `#37474F`）+ Streamlit 暗主题（bg `#0e1117` / panel `#262730`）。组件抽象：

- `<PageTitle> / <Subheader> / <Caption>` 对应 `st.title/subheader/caption`
- `<Metric label value delta>` 对应 `st.metric`，含 ▲▼ 着色 + `inverse` 反向语义
- `<Info> / <ErrorBox> / <Warning>` 对应 `st.info/error/warning`
- `.df` 表格类对齐 `st.dataframe`（hover 行、`pnl-pos/pnl-neg` 着色）
- `<StatusBadge>` 把 `queued/running/succeeded/failed/cancelled` 映射到语义色背景

### i18n

`src/i18n.ts` 仿 `tradingbot/dashboard/i18n.py`，key 命名空间对齐（`app.* / nav.* / qt.* / sig.* / status.* / table.*`），默认中文，切换写 localStorage。

### 路由守卫

- `RequireAuth`：未登录跳 `/login?next=`（loader 阻塞一次 `/auth/me`）。
- `RequireRole(['admin'])`：包裹 `/admin/*`，非 admin 显示无权限卡。

---

## 块 3：模型设置受控下拉 + 分析结果可视化

**提交**：`bc5c625 feat(web): improve model settings and analysis reports`（+1414 / -139）

### 模型设置改造（`web/src/routes/settings/model.tsx`）

之前是手敲 provider / 模型 ID 的纯文本输入，容易拼错。改成：

1. 并行拉 `GET /settings/model/options`（catalog）+ `GET /settings/model`（当前用户配置）。
2. **Provider**：下拉，文案用后端 label；切换 provider 时按该 provider 的默认值重置 backend_url、quick/deep。
3. **Quick / Deep 模型**：下拉，候选来自 `provider.{quick,deep}_models`；`supports_custom_model=true` 时追加"自定义…"选项弹出输入框。
4. **Backend URL**：默认填 `default_backend_url`；`backend_url_editable=false` 时只读 + "由服务端固定"说明。
5. **API Key**：`required_env_var=null` 的 provider（ollama）直接隐藏 key 输入并显示"不需要"提示。
6. **回填**：用户已有模型 ID 不在候选里时自动落到"自定义"并填入旧值，防止数据丢失。
7. **保存**：组装时把"自定义"占位替换成真实输入；空 backend_url 传 `null`；空 api_key 不发送字段（保留旧 key）。

### 分析结果重做

之前详情页用 `JSON.stringify(reports)` 一坨灰字。改成：

- **`<DecisionCard>`**（`web/src/components/run/DecisionCard.tsx`，92 行）
  顶部彩色大卡，正则从 `final_trade_decision / trader_investment_plan` 抓出 Rating / Action / Entry / Stop / Target / Position Sizing / Time Horizon，按 5 档信号配色（BUY/OVERWEIGHT 绿、HOLD 灰、UNDERWEIGHT 黄、SELL 红），并拉出 Executive Summary 摘要。
- **`<AgentReportTabs>`**（96 行）
  仿 Streamlit `signals_view._render_agent_tabs`，7 个 emoji tab：🎯组合经理 / 📊行情 / 📰新闻 / 💬情绪 / 📈基本面 / ⚖️研究经理 / 💼交易员，自动跳过空内容，激活 tab 用 Streamlit 红下划线。
- **`<Markdown>`**（13 行 + 28 行 prose CSS）
  `react-markdown` + `remark-gfm`，支持 GFM 表格、删除线、自动链接。配套 `.prose-md` 暗色排版：h1~h4 分级、表格深底浅边、code/pre 等宽、blockquote info 蓝条、链接 Streamlit 红。

新增依赖：`react-markdown ^10.1`、`remark-gfm ^4.0`。

---

## 块 4：Worker Markdown 报告输出

**提交**：`f542e98 fix(api): write markdown reports for analysis runs`、`4ce8dee chore(git): ignore generated reports`

### 动机

worker 跑完任务后，DB 里只有 `final_state` JSON。要让用户能查看历史报告 / 外部消费，需要按 `tradingbot/` 的旧 `reports/` 树结构落 Markdown 文件。

### 新增

- `tradingagents/reports.py`（111 行）：按 `reports/{TICKER}_{YYYYMMDD_HHMMSS}/{1_analysts,2_research,3_trading,4_risk,5_portfolio}/*.md` 输出每个 agent 的报告 + 顶层 `complete_report.md` 汇总。
- `tradingagents/default_config.py`：新增 `reports_dir` 配置项指向输出根目录。
- `tradingagents/worker/analysis.py`：成功后调用 reports writer，把 final_state 各 section 落到磁盘。
- `tests/worker/test_jobs.py`：+66 行覆盖 reports 写入。

### .gitignore

`4ce8dee` 把 `reports/` 加进 `.gitignore`，并删除历史误提交的 SPY/TSLA 报告文件树（-8847 行）。生成物以后不再入库。

---

## 块 5：MiniMax 接入加固（未提交）

### 5.1 `reasoning_split` 走 `extra_body`

**症状**：`/settings/model/validate` 触发 `Completions.create() got an unexpected keyword argument 'reasoning_split'`。

**根因**：`MinimaxChatOpenAI._get_request_payload` 给 M2.x reasoning 模型把 `reasoning_split=True` 直接 setdefault 到 payload 顶层。`openai` SDK 当前版本对 `Completions.create()` 做严格 kwarg 白名单校验，任何非标字段直接 TypeError，与是否走 reasoning 模型无关。

**修复**：把 `reasoning_split` 移进 `extra_body`（openai SDK 设计上专门用于透传非白名单请求体字段的入口，会被原样合并进 JSON body）：

```python
extra_body = dict(payload.get("extra_body") or {})
extra_body.setdefault("reasoning_split", True)
payload["extra_body"] = extra_body
```

**测试**：`tests/test_minimax.py` 三处断言从 `payload["reasoning_split"]` 改成 `payload["extra_body"]["reasoning_split"]`，并加 "顶层永远不再有 reasoning_split" 防回归断言。`pytest tests/test_minimax.py tests/test_capabilities.py` 27/27 通过。

### 5.2 minimax-cn URL 从 `/anthropic` 回退到 `/v1`

**症状**：保存 minimax-cn 配置时 backend_url 默认值被改成了 `https://api.minimaxi.com/anthropic`，OpenAI 兼容客户端打到 Anthropic 兼容端点全部失败。

**根因**：某次提交把三处都改成了 `/anthropic`：
- `_PROVIDER_BASE_URL["minimax-cn"]`
- `ProviderSeed("minimax-cn", ...)` 默认值
- `db.py` 启动迁移会把已落库的 `/v1` 强行 UPDATE 成 `/anthropic`

中国站 OpenAI 兼容是 `/v1`，Anthropic 兼容是 `/anthropic/v1/messages` 且鉴权头从 `Authorization: Bearer` 变 `X-Api-Key`，两者不能互换。

**修复**：三处全部改回 `/v1`，启动迁移改成反向：

```python
"UPDATE user_model_settings "
"SET backend_url = 'https://api.minimaxi.com/v1' "
"WHERE llm_provider = 'minimax-cn' "
"AND backend_url = 'https://api.minimaxi.com/anthropic'"
```

启动时 `ensure_additive_schema()` 自动跑这条修复，无需手动处理脏数据。实测重启后 PG 表里 admin 用户的脏行已自动归位。

### 5.3 CN 模型目录与官方支持列表对齐

**症状**：SPA "MiniMax China" 下拉里列了 `M2.5-highspeed / M2.1-highspeed / MiniMax-M2`，这些 ID 不在 `platform.minimaxi.com` 官方支持列表里。

**根因**：`_MINIMAX_MODELS` 同时给国际站和国内站复用，按 `platform.minimax.io`（国际）抄的，但中国站 OpenAI 兼容端点官方文档（`text-chat-openai`）明确只列 4 个：`MiniMax-M2.7 / M2.7-highspeed / M2.5 / M2.1`。

**修复**：新建 `_MINIMAX_CN_MODELS` 严格按官方 4 个 ID 排，`minimax-cn` 改用新列表；国际站 `minimax` 继续用原 `_MINIMAX_MODELS`。`M2.7-highspeed` label 加 "(Highspeed plan only)" 警示。

### 5.4 用户层面 429 真因

`Token Plan Max (0/0 used)` 错误并非配额耗尽，是用户保存了 `quick_think_llm = MiniMax-M2.7-highspeed`，而 `M2.7-highspeed` 属于 MiniMax "Highspeed" 子套餐（Plus Highspeed $40/月、Max-Highspeed $80/月、Ultra-Highspeed $150/月），各有独立配额计数器，跟常规账户配额完全两套。用户的账户没订阅 Highspeed 子套餐，所以该模型分母直接为 0。接入侧已通过 5.3 把不该选的从下拉移除 + 加 label 警示；订阅状态需用户自助到 `platform.minimaxi.com` 处理。

---

## 块 6：目录数据流自愈 + 补齐 backend_url

### 6.1 `ensure_seeded()` 始终全量重建 model_options

**症状**：修完 `_MINIMAX_CN_MODELS` 重启 API，下拉仍是旧 8 个 ID。

**根因**：`LLMModelCatalogRepository.ensure_seeded()` 原逻辑——如果 provider 表非空就早 return，model_options 永远不再 rebuild。设计意图是"已 seed 过就跳过"，但导致 Python catalog 任何后续变更都不会传播到 DB，每改一次模型 ID 就要手写一次 `DELETE/INSERT` 迁移。

**修复**：去掉早 return，每次进程冷启动按 `MODEL_OPTIONS` 全量重建所有 provider 的 `llm_model_options` 行。

**安全性论证**：
- 成本：14 provider × ~5 行 ≈ 70 INSERT，`self._seeded` 每实例只跑一次。
- 外键：`user_model_settings.{quick,deep}_think_llm` 是普通 String 字段，**不外键到 `llm_model_options`**，重建不会级联。
- 唯一约束：`UniqueConstraint(provider_id, mode, model_id)` 保留，并发冷启动最坏 case 是第二个请求 IntegrityError 一次后由前端 retry 解决。
- 用户已保存配置：catalog 重建后若用户的 `quick_think_llm` 不在新列表里，`GET /settings/model` 仍返回旧值（不校验），但 `PUT` 走 `validate_model_settings()` 时 422，强制用户重选。这是期望行为。

**工程价值**：以后改 `MODEL_OPTIONS` 只要改 Python 然后重启，目录漂移问题自愈。

### 6.2 补齐 openai / google / anthropic 的 `default_backend_url`

之前三条 seed 的 `default_backend_url` 都是 `None`，功能上不影响调用（langchain SDK 内部有默认值），但 SPA 模型设置页 Backend URL 输入框空白，用户无从知道实际打到哪个端点。

按官方文档补齐：

```python
ProviderSeed("openai",    "OpenAI",    "https://api.openai.com/v1"),
ProviderSeed("google",    "Google",    "https://generativelanguage.googleapis.com/v1beta"),
ProviderSeed("anthropic", "Anthropic", "https://api.anthropic.com"),  # 不带 /v1，SDK 自己拼版本路径
```

Azure 保持 `None + editable=True`，因为它按客户 deployment 拼 URL，没有通用默认。

`ensure_seeded()` 的 provider 表 upsert 已包含 `default_backend_url`（这部分一直是 upsert，没有早 return 缺陷），重启后立即生效。实测 14 个 provider 全部带正确 URL（azure 除外）。

---

## 块 7：前端二次打磨（未提交）

### 7.1 设置抽屉移到右上角悬浮

原 Sidebar 顶部那一大块设置入口（语言切换 / 已登录用户 / 登出 / 设置 / 管理员）全部搬到 `<SettingsDrawer>`，由 `<AppLayout>` 右上角悬浮按钮触发。Sidebar 砍掉这些只剩纯功能导航（分析 / 交易 / 自选股 / 快速下单）。

**新文件**：
- `web/src/components/ui/Drawer.tsx`（58 行）：通用抽屉，支持左/右侧、遮罩点击关闭、ESC 关闭、200ms 滑入动画
- `web/src/components/layout/SettingsDrawer.tsx`：包语言切换 + 用户块 + 设置/管理员两组导航 + 点击自动关闭跳页

**辅助修复**：语言切换那一行用 `flex-nowrap whitespace-nowrap` + `shrink-0`，select 宽度 `w-32` 容纳 "English"，杜绝中英文切换时换行。

### 7.2 `<RunProgress>` 进度可视化

**新文件**：`web/src/components/run/RunProgress.tsx`（135 行）

任务运行时不再只是一坨 SSE 文本流，而是按 phase 渲染 stepper：排队中 → 准备环境 → 智能体分析 → 整理报告 → 完成 / 失败 / 取消，从 `run_progress` 事件取百分比与 message，从 `current_step` 取当前步骤。失败/取消有专用标题与样式。

**配套后端改动**：
- `tradingagents/api/repositories.py`：新增 `AnalysisRunRepository.record_progress(run_id, phase, step, percent, message)` 写一条 `run_progress` 事件到 `run_events` 表。
- `tradingagents/worker/jobs.py`：在 `execute_analysis_run` 的 3 个关键节点（准备前、分析中、保存前）各 commit 一条 progress。
- 测试同步在 `tests/api/test_repositories.py`、`tests/worker/test_jobs.py` 中扩展。

### 7.3 i18n 全量覆盖

`web/src/i18n.ts` 从初版 ~80 行扩到 267 行（+186 行新 key）。新增命名空间：

- `analysis.*` —— 创建任务表单 / 详情页 / 失败原因
- `table.*` —— 通用表格列名（ticker / trade_date / status / created_at / finished_at / username / role / enabled / sessions / details / no_matches）
- `status.*` —— 五种 run 状态本地化（queued/running/succeeded/failed/cancelled）
- `run.stage.* / run.message.* / run.title.*` —— 进度 stepper 各阶段文案
- `report.*` —— 7 个 agent tab 标签 + 描述
- `decision.*` —— DecisionCard 各字段
- `markdown.empty / settings.* / admin.* / common.load_failed` 等通用补漏

所有页面（list / new / detail / settings/model / settings/account / admin/users / admin/runs / DecisionCard / AgentReportTabs / RequireRole / Drawer / SettingsDrawer）的硬编码中文文案都迁到 `t()` 调用。

---

## 整体回归测试

| 类别 | 命令 | 结果 |
|---|---|---|
| MiniMax 客户端单元 | `pytest tests/test_minimax.py tests/test_capabilities.py` | 27/27 ✓ |
| 模型目录 repo | `pytest tests/api/test_model_catalog_repository.py` | 全过 ✓ |
| 模型设置路由 | `pytest tests/api/test_model_settings_routes.py` | 全过 ✓ |
| Worker / progress | `pytest tests/worker/test_jobs.py` | 全过 ✓ |
| 前端类型 | `pnpm exec tsc --noEmit` | 0 errors ✓ |
| 集成 | `curl /settings/model/options` 登录后 | 14 provider 全带 backend_url（azure 除外），minimax-cn 仅 4 个官方 ID ✓ |
| DB 反向迁移 | `SELECT * FROM user_model_settings WHERE backend_url='/anthropic'` | 0 行 ✓ |
| 端到端 SPA | `http://localhost:5173` 登录、新建分析、模型设置、admin 全流程 | OK ✓ |

## 后续

- `ensure_seeded()` 改成 `@app.on_event("startup")` lazy → eager，消除冷启动并发 race。
- 用户已保存模型 ID 不在 catalog 时，`GET /settings/model` 加 `warnings: [...]`，让 SPA 显示横幅。
- `MinimaxChatOpenAI` 对 `max_completion_tokens` 做 clamp（中国站硬上限 2048）。
- Phase 3 后端补 `GET /runs`（当前用户视角）、`/portfolio/* /performance/* /trades/* /risk/* /orders /config`，把 SPA 占位页 4 个面板和右上 Quick Trade 接通。
- Streamlit 与 SPA 账号体系合并策略评估。

## 参考资料

- [MiniMax 中国 OpenAI 兼容 API 文档](https://platform.minimaxi.com/docs/api-reference/text-chat-openai.md)
- [MiniMax 中国 Anthropic 兼容 API 文档](https://platform.minimaxi.com/docs/api-reference/text-chat-anthropic.md)
- [MiniMax Token Plan 介绍（Highspeed 子套餐分层）](https://platform.minimax.io/docs/token-plan/intro)
- [OpenAI API 默认 base URL](https://developers.openai.com/api/reference/overview)
- [langchain-anthropic ChatAnthropic 默认 base_url](https://reference.langchain.com/python/langchain-anthropic/chat_models/ChatAnthropic/anthropic_api_url)
- [Gemini API `generativelanguage.googleapis.com/v1beta`](https://ai.google.dev/api)
- 内部 spec 链：`2026-05-27-user-model-settings-design.md`、`2026-05-26-analysis-api-auth-multitenancy.md`、`2026-05-26-analysis-http-api-design.md`
