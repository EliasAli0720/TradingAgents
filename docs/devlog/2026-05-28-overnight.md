# 开发日志 — 2026-05-28（凌晨 2 点 → 当日）

分支：`phase/8-increase-concurrency-for-analysis-functions`

本次开发跨两大主题：**(一) 分析任务的并发/队列工程化**（凌晨起），**(二) 报告多语言翻译**（下午起，含独立翻译模型）。共 15 个提交，下面按时间线 + 主题归纳。

---

## 主题一：分析任务并发与队列工程化

目标：支持多个分析任务安全并发，引入排队、公平调度、容量限制、心跳/兜底、运行隔离、实时事件流，以及取消。

### 提交时间线

| 提交 | 时间 | 内容 |
|---|---|---|
| `04fea95` | 01:51 | feat(api): add analysis capacity schema —— 容量相关 schema（系统/单用户运行数、队列上限） |
| `18b25e6` | 02:17 | feat(api): queue analysis runs before dispatch —— 创建 run 先入队（queued），不再立即跑 |
| `42db44a` | 02:32 | feat(worker): dispatch analysis runs fairly —— 公平调度器（按用户轮询 + 优先级 + 创建时间），租约领取 |
| `c6a4a97` | 09:59 | feat(worker): add run heartbeat and sweeper —— 运行心跳 + 清扫器回收僵死/超租约任务 |
| `648993c` | 10:05 | feat(api): isolate analysis artifacts by run —— 产物按 run 隔离存储（artifact store + 表） |
| `a257d57` | 10:10 | feat(api): store analysis memory in database —— 分析记忆（reflection/past context）落 PG（`analysis_memory_entries`） |
| `1b11fde` | 10:17 | feat(graph): add run context cancellation —— graph 层注入 run context + 协作式取消 |
| `952132b` | 10:25 | feat(worker): limit provider concurrency —— 按 provider 限制并发，避免打爆配额 |
| `d9aebb2` | 14:39 | feat(api): stream run events through redis —— run 事件经 Redis pub/sub 实时分发（SSE 背后） |
| `8994351` | 15:35 | feat(api): expose capacity and artifacts —— 暴露容量查询与产物列表/下载端点 |
| `c5d0f3e` | 15:44 | feat(web): show queued runs and artifacts —— 前端展示排队状态、队列位次、产物 |
| `7d1c4b6` | 15:51 | chore(worker): wire queue scheduler startup —— 启动时挂载队列调度（dispatch/sweep 周期任务） |
| `9ae9f91` | 16:10 | fix(worker): cancel dispatching runs immediately —— dispatching 态可立即取消 |

### 关键设计点

- **状态机扩展**：run 状态从 `queued/running/succeeded/failed/cancelled` 扩到含 `dispatching`、`cancelling`，配套 `priority / attempt_count / max_attempts / dispatched_at / heartbeat_at / lease_expires_at / current_phase / progress_percent / updated_at`（`ensure_additive_schema` additive 迁移）。
- **公平调度**：`users_with_queued_runs` 用窗口函数按用户取队首，再按 priority/created_at 排序；`claim_next_queued_for_dispatch` 用乐观 `UPDATE ... WHERE status='queued'` + rowcount 抢占，避免并发重复领取。
- **容量闸**：系统级 `max_running_system`、单用户 `max_running_per_user`、队列 `max_queued_per_user`。
- **健壮性**：worker 心跳续租 + sweeper 回收超租约任务（崩溃可恢复，配合 graph 的 checkpointer）。
- **实时事件**：run 事件写 `run_events` 表 + 经 Redis pub/sub 推给 SSE 订阅者；前端 `useRunEvents` 消费 `run_queued/dispatching/started/progress/...` 渲染进度。
- **取消**：协作式——`cancel` 把运行中任务标 `cancelling`，worker 在节点边界检查并 `mark_cancelled`；dispatching/queued 态可即时取消。

---

## 主题二：报告多语言翻译

目标：英文报告生成后，按用户语言输出中文；用独立翻译模型，不占用分析模型。

### 提交

| 提交 | 时间 | 内容 |
|---|---|---|
| `9e7c96f` | 16:26 | feat: incremental report translation in user's language —— 增量翻译主体 |
| `1dcac8e` | （当日） | feat: dedicated translation model + report render fixes —— 独立翻译模型 + 渲染修复 |

### `9e7c96f` 增量翻译

- **语言偏好落库**：`users.language`（默认 zh），`/auth/me`+login 返回；新增 `PUT /settings/preferences`。SPA 切换即落库、登录同步。
- **流式中途翻译**：`TradingAgentsGraph.propagate(on_section_ready=cb)` 用 `graph.stream()`（`stream_mode="values"`，chunk 是完整累积态）检测每个 report section 首次出现即回调；分析师报告在 pipeline 中途就翻，跑完只剩末尾几段兜底。
- **存储**：独立暂存表 `analysis_run_translations(run_id, lang, section, content)`，与 result 行解耦（result 行成功才创建，而中途译文需提前落地）；英文原文留在 `AnalysisRunResult.reports`，从不复制。
- **可替换翻译器**：`tradingagents/translation.py` 的 `ReportTranslator` 协议 + `LLMReportTranslator`；幂等 + best-effort（单段失败回退英文）。
- **前端**：`AgentReportTabs` 逐段 `reports_i18n[lang]?.[section] ?? reports[section]`；轮询直到全部段翻完；`DecisionCard` 结构化字段仍解析英文锚点。

### `1dcac8e` 独立翻译模型 + 渲染修复

- **独立翻译模型**（与分析模型分开）：
  - 新表 `user_translation_settings`（单模型）+ `UserTranslationSettingsRepository`。
  - `translation_catalog.py` 固定 3 选项：openai/gpt-4o-mini、deepseek/deepseek-chat(V3)、google/gemini-2.5-pro，provider↔model 必须配对。
  - 端点镜像 `/settings/model`：`/settings/translation` 的 options/get/put/delete-key/validate（validate 复用 `model_probe` 的 pong 探测）。
  - worker `translate_section` 优先用翻译模型，未配置才回退分析模型。
  - 前端 `/settings/translation` 页 + 抽屉「翻译模型」入口 + i18n。
- **校验展示统一**：抽出共享 `ValidationResultCard/ValidationErrorCard`，翻译页与模型页用同一套按 `probe_status` 分色分标题的校验卡（去重 model.tsx）。
- **Markdown 渲染修复**：翻译模型有时把整段输出用 ```` ```markdown ``` ```` 围栏包住（被当代码块渲染、原样显示 `#`/`**`）或 echo 了 prompt 分隔符。
  - 源头：`_clean_translation_output` 去围栏 + 去分隔符；prompt 明确禁止包裹。
  - 兜底：前端 `Markdown` 组件渲染前自动拆掉单层围栏 —— 让已存的脏 run 刷新即恢复。

---

## 数据库变更汇总（均 additive / 新表，create_all 或 ensure_additive_schema）

| 对象 | 变更 |
|---|---|
| `analysis_runs` | 新增 priority / attempt_count / max_attempts / current_phase / progress_percent / dispatched_at / heartbeat_at / lease_expires_at / updated_at |
| `analysis_run_artifacts` | 新表：按 run 隔离的产物元数据 |
| `analysis_memory_entries` | 新表（+ raw_return/alpha_return/holding_days/reflection 列） |
| `analysis_run_translations` | 新表：逐段翻译暂存 (run_id, lang, section, content) |
| `users.language` | 新列，默认 zh |
| `user_translation_settings` | 新表：独立翻译模型设置 |

> 历史遗留：早期临时给 `analysis_run_results` 加过 `reports_i18n` 列，后改为独立暂存表，该列废弃但无害。

## 测试与验证

- 后端全量 **416 passed, 1 skipped**（live API 跳过）；前端 `tsc --noEmit` 0 错。
- 新增覆盖：调度/心跳/清扫/容量/取消、SSE 事件、翻译清洗与设置端点、preferences 端点。

## 已知 / 后续

- dev worker `--concurrency=1`：流式中途翻译实际排在分析任务后串行执行，"边分析边翻"的并行收益需多 worker / 提高并发才体现。
- 翻译"未配置回退分析模型"是优雅降级；如需严格"未配置就不翻"可改为跳过 + 提示。
- `ensure_seeded` 冷启动并发 race（catalog 重建）可改 `@app.on_event("startup")` eager 消除。
- Phase 3 待办：`GET /runs`（当前用户视角）、交易侧端点（portfolio/performance/trades/risk/orders/config）接通 SPA 占位页。

## 相关 spec

- `docs/superpowers/specs/2026-05-28-model-integration-hardening.md`
- `docs/superpowers/specs/2026-05-28-report-translation-design.md`
