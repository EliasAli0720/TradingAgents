# 分析报告多语言输出设计

日期：2026-05-28

分支：`phase/7-service-engineering`

依赖前置：
- `2026-05-27-user-model-settings-design.md`（用户模型配置 + run 上的 `llm_config` 快照）
- `2026-05-28-model-integration-hardening.md`（run_progress 事件链路、SPA i18n、reports 数据流）

## 目标

英文分析报告生成完成后，用**用户自己配置的模型**把报告翻译成目标语言（当前为中文），双语都留存。SPA 按用户的系统语言设置输出对应语言的报告。用户语言设置落库。

> **实现升级（完整版 / 增量翻译）**：最终实现把翻译触发点从"run 成功后整篇翻"前移到"流式过程中逐段翻"。pipeline 用 `graph.stream()`（`stream_mode="values"`，每个 chunk 是完整累积状态）检测每个 report section 首次出现，立即对该段发起翻译。分析师阶段（market/news/sentiment/fundamentals，文本大头）在中途就翻完，跑完后只剩 3 段短决策兜底翻译，"翻译中"等待基本消除。配额成本不在本次关注范围（用户确认）。下文"实现说明"小节描述最终落地架构，与上面早期设计的差异处以实现为准。

## 已确认决策

- **不动原文**：英文 `reports` 一字不改，是唯一真源。
- **翻译时机**：英文报告生成并标记 run 成功**之后**，作为独立步骤翻译。
- **翻译器**：先用用户 run 快照里的模型（`llm_config`）翻译；翻译逻辑抽成可替换接口，**后续若效果不好可切换成专用翻译 API，只改一个实现文件**。
- **存储**：additive，新增 `reports_i18n`，不碰 `reports`。
- **语言来源**：per-user 设置，**落库**到 `users.language`。
- **输出选择**：前端按当前语言在 `reports_i18n[lang]` 与 `reports`（英文回退）之间选。

## 非目标

- 不接入专用翻译 API（DeepL / 机器翻译服务）——预留接口，第一版不实装。
- 不做整篇一次性翻译（受 MiniMax 中国站 `max_completion_tokens` 2048 上限制约，逐段翻）。
- 不翻译 `final_state`（只翻 7 个面向用户的 report 字段）。
- 不为历史 run 回填翻译；老 run 的 `reports_i18n` 为空，前端自然回退英文。

---

## 一、用户语言设置落库

### 数据模型

`users` 表加列（additive 迁移，写进 `ensure_additive_schema`）：

```sql
ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'zh'
```

取值 `'zh' | 'en'`，默认 `'zh'`（与 app 默认语言一致）。

### API

- `GET /auth/me` 响应加 `language` 字段。
- 新增 `PUT /settings/preferences`（需登录 + CSRF）：
  ```json
  { "language": "zh" }
  ```
  校验枚举 `{zh, en}`，写 `users.language`，返回 `204`。

### 前端

- 右上角语言切换 `setLang()` 时：① 立即写 localStorage（即时生效），② 调 `PUT /settings/preferences` 落库。localStorage 是即时缓存，DB 是真源。
- 登录后 `useAuth()` 从 `GET /auth/me` 读 `language`，若与 localStorage 不一致以 DB 为准并同步。

---

## 二、翻译链路（链式 Celery 任务）

### 流程

```
execute_analysis_run(run_id)
  ├─ 跑英文 pipeline
  ├─ save_analysis_report(final_state)          # 英文落盘
  ├─ store_success(reports=英文, final_state)    # run → succeeded，英文立刻可看
  └─ celery: translate_run_reports.delay(run_id) # 链式投递，不阻塞 run 成功

translate_run_reports(run_id)                    # 新 Celery 任务
  ├─ 读 run.llm_config 快照（用户自己的模型 + key）
  ├─ 对每个 report 字段调 translator.translate(text, target="zh")
  ├─ repo.store_translations(run_id, lang="zh", reports_i18n=...)
  └─ repo.add_event(run_id, "reports_translated", {"lang": "zh"})
```

**为什么拆成链式任务**：英文是真源，先让英文可看不被翻译延迟阻塞；翻译是 best-effort，失败只影响译文不影响 run 成功。SPA 收到 `reports_translated` SSE 事件后刷新结果即可。

### Translator 接口（可替换）

新文件 `tradingagents/translation.py`：

```python
class ReportTranslator(Protocol):
    def translate(self, markdown: str, *, target_lang: str) -> str: ...

class LLMReportTranslator:
    """用用户自己的模型翻译。第一版实现。"""
    def __init__(self, llm_config: dict): ...
    def translate(self, markdown: str, *, target_lang: str) -> str:
        # 用 quick_think_llm 模型，逐段翻译
        ...

# 后续要换专用翻译 API，只新增一个实现类、改工厂一行：
# class ApiReportTranslator: ...
```

worker 通过工厂拿 translator，业务代码不感知具体实现。

### 翻译模型与 prompt

- **用 `quick_think_llm`**（机械活、省成本）。
- prompt 约束：
  - 翻译成简体中文（目标语言参数化）。
  - **保留所有 Markdown 结构**：标题层级、表格、列表、代码块、加粗。
  - 保留数字、百分比、ticker 代码、`$` 金额原样。
  - 技术指标缩写（MACD/RSI/EPS 等）保留英文。
  - 只输出译文，不要解释。
- **逐段翻**而非整篇：MiniMax 中国站 `max_completion_tokens` 上限 2048，长报告整篇会被截断。逐段还能并发提速。若单段仍超限，按段落/标题二次切分（实现时处理）。

### 失败处理

- 单段翻译失败：跳过该段，`reports_i18n["zh"]` 缺这个 key，前端回退英文。
- 整任务失败：`reports_i18n` 留空，记 warning 日志，**不影响 run 的 succeeded 状态**。
- translate_run_reports 自身设 `max_retries`，但不重试到阻塞；翻译不是关键路径。

---

## 三、存储（additive）

### 数据模型

`run_result` 加列：

```sql
ALTER TABLE run_result ADD COLUMN reports_i18n JSON
```

结构：

```json
{
  "zh": {
    "market_report": "## 行情分析\n...",
    "news_report": "...",
    "final_trade_decision": "...",
    ...
  }
}
```

`reports`（英文）保持不变。`reports_i18n` 默认 NULL。

### Repository

`AnalysisRunRepository.store_translations(run_id, lang, reports)`：把 `reports_i18n[lang]` 写入（merge，不覆盖其他语言）。

### API

`GET /runs/{id}/result` 响应 additive 加 `reports_i18n`：

```json
{
  "run_id": "...",
  "status": "succeeded",
  "decision": "OVERWEIGHT",
  "reports": { ...英文... },
  "reports_i18n": { "zh": { ...中文... } },
  "final_state": { ... }
}
```

---

## 四、前端取数

### 选择逻辑

- `AgentReportTabs`：每个 tab 内容取 `reports_i18n[lang]?.[key] ?? reports[key]`（有译文用译文，否则英文回退）。
- 语言切换是纯前端动作，两份数据都已在手，**即时切换无需重新请求**。
- 监听 `reports_translated` SSE 事件 → invalidate `['runResult', runId]` 重新拉一次拿到译文。

### DecisionCard 的坑（必须守住）

`DecisionCard` 靠正则抓英文 `**Rating**: BUY`、`**Entry Price**:` 这类锚点。译文没有这些英文标记。所以：

- **信号 / 动作 / 入场价 / 止损 / 目标 / 仓位 / 周期 这些结构化字段永远从英文 `reports` 解析**（语言无关）。
- 字段标签本来就走 i18n（`decision.*` key）。
- 只有 Executive Summary 叙述段，若 `reports_i18n[lang]` 有则显示译文版。

---

## 五、迁移清单

| 表 | 变更 | 位置 |
|---|---|---|
| `users` | `+ language TEXT NOT NULL DEFAULT 'zh'` | `ensure_additive_schema` |
| `run_result` | `+ reports_i18n JSON NULL` | `ensure_additive_schema` |

两者都 additive，历史数据安全：老用户 language 默认 zh，老 run 的 reports_i18n 为空、前端回退英文。

---

## 六、实现任务拆解（TDD，bite-sized）

1. **users.language 落库**
   - 迁移加列 + `User` model 字段
   - `GET /auth/me` 返回 language
   - `PUT /settings/preferences` 端点 + 校验 + 测试
2. **前端语言落库**
   - `setLang()` 调 `PUT /settings/preferences`
   - 登录后从 `/auth/me` 同步 language
3. **Translator 接口 + LLM 实现**
   - `tradingagents/translation.py`：Protocol + `LLMReportTranslator`（逐段、quick 模型、prompt）
   - 单测：mock LLM，验证 Markdown 结构保留、逐段调用、失败跳过
4. **run_result.reports_i18n 存储**
   - 迁移加列 + `store_translations` repo 方法 + 测试
5. **translate_run_reports Celery 任务**
   - 链式投递 + 读 llm_config + 写 reports_i18n + emit 事件
   - worker 测试
6. **API 返回 reports_i18n**
   - `RunResultResponse` schema additive 字段
7. **前端消费**
   - `AgentReportTabs` 译文回退、`DecisionCard` 英文锚点解析、监听 `reports_translated` 刷新

## 七、后续

- 换专用翻译 API：新增 `ApiReportTranslator` 实现 `ReportTranslator`，改工厂一行；其余不动。
- 多语言扩展：`reports_i18n` 已是 `{lang: {...}}` 结构，加语种只是多翻一轮。
- 翻译质量评估：可加一个"重新翻译"按钮，admin 触发 `translate_run_reports` 重跑。
- 成本控制：可选只在用户 language≠en 时才触发翻译任务（英文用户不付翻译成本）。

## 实现说明（最终落地架构）

与早期"post-run 整篇翻 + reports_i18n 列"的设计相比，最终落地为"流式增量翻 + 独立暂存表"：

### 存储：独立暂存表（取代 reports_i18n 列）

`analysis_run_translations(run_id FK, lang, section, content, created_at)`，复合主键 `(run_id, lang, section)`。因为 result 行要等 `store_success` 才创建，而分析师报告在 run 成功**之前**就翻好了，译文需要一个不依赖 result 行的落点。English 原文仍在 `AnalysisRunResult.reports`，从不复制。新表由 `init_db` 的 `create_all` 自动建，无需额外迁移（早期临时加的 `reports_i18n` 列已废弃，遗留 orphan 列无害）。

### 流式触发：graph 回调

- `TradingAgentsGraph.propagate(..., on_section_ready=cb)`：非 debug 路径若提供回调则走 `graph.stream()`，每个 section（`REPORT_KEYS`）首次出现非空字符串时 `cb(section, text)` 触发一次。回调异常被吞，不影响 run。
- `run_tradingagents_analysis(..., on_section=cb)` 透传；仅在 `on_section` 非空时传 `on_section_ready`，保持对旧测试桩 / 调用方的向后兼容。

### Worker 编排

- `run_analysis_task`：先取 owner 语言（`_run_target_language`，英文返回 None → 全程跳过翻译）。非英文时构造 `on_section` 回调，回调内 `translate_section_task.apply_async(run_id, lang, section, text)`，把每段翻译投到独立队列（不阻塞分析流）。
- run 成功后**兜底**：遍历 `result.reports`，对尚未翻译的 section 再补投（覆盖最后一波 + 中途漏的）。
- `translate_section(repo, run_id, lang, section, text)`：幂等（`has_translation` 已存在则跳过）+ best-effort（翻译异常静默跳过，前端回退英文）。emit `section_translated` 事件。

### Repository

- `upsert_translation(run_id, lang, section, content)`：写一段译文 + emit 事件。
- `get_translations(run_id) -> {lang: {section: content}}`：从暂存表组装。
- `has_translation(...)`：幂等检查。

### API / 前端

- `GET /runs/{id}/result` 的 `reports_i18n` 由 `repo.get_translations(run_id)` 组装（非 result 列）。
- 前端 detail.tsx 轮询 result 直到当前语言译文齐（English 不轮询），`AgentReportTabs` 逐段 `reports_i18n[lang]?.[section] ?? reports[section]` 回退。分段译文随翻随显。

### 注意

- `tradingagents/graph/trading_graph.py` 在回调分支里 `from tradingagents.api.serialization import REPORT_KEYS`（惰性 import，避免 core→api 的 import-time 耦合）。
- `section_translated` 事件在 `run_succeeded` 之后仍可能继续发，但 SSE 流在终止事件时已关闭，所以前端靠轮询而非该事件刷新。

### 测试

- `tests/test_translation.py`：translator 空文本跳过 / 返回内容 / 逐段失败隔离。
- `tests/worker/test_jobs.py`：`translate_section` 落暂存表且不碰英文、幂等、英文 owner 跳过（`_run_target_language`）。
- `tests/api/test_model_settings_routes.py`：login/me 带 language、`PUT /settings/preferences` 落库 / 422 / 鉴权。
- 全量 410 passed，前端 `tsc --noEmit` 0 错。

## 参考

- 内部：`2026-05-28-model-integration-hardening.md`（run_progress 事件、SPA i18n、reports 数据流、MiniMax 2048 输出上限）
- 内部：`2026-05-27-user-model-settings-design.md`（llm_config 快照机制）
