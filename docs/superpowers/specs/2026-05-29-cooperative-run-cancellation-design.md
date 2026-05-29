# 分析任务协作式取消设计

日期：2026-05-29

分支：`phase/8-increase-concurrency-for-analysis-functions`

## 背景

当前 `POST /runs/{run_id}/cancel` 已能更新 API 状态机：

- `queued` 和 `dispatching` run 会进入 `cancelled`。
- `running` run 会进入 `cancelling`，并尝试 Celery revoke。
- worker 在分析函数返回后会检查 run 状态；如果看到 `cancelling`，最终标记为 `cancelled`，不会写入成功结果。

问题是：如果任务已经进入 `TradingAgentsGraph.propagate()`，graph 执行路径没有接入取消信号。用户取消后，后台仍可能继续执行后续 analyst、researcher、trader、risk、portfolio manager，以及报告翻译投递。最终结果不会保存，但 LLM token、数据接口和 worker 时间仍会被浪费。

本设计采用协作式取消：不强杀 worker 进程，而是在 graph 节点边界尽快停止后续执行。

## 目标

- 用户取消 `running` run 后，worker 不再进入后续 graph 节点。
- 当前已经发出的单个 LLM 或数据 provider 请求允许自然返回或超时；返回后立即停止后续节点。
- 取消后不保存 `AnalysisRunResult`。
- 取消后不继续投递新的 `translate_section_task`。
- 保持现有 API 响应语义：`running -> cancelling -> cancelled`。
- 复用现有 `CancellationToken`、`RunContext` 和 `GraphSetup._cancellable()` 结构。

## 非目标

- 不默认使用 Celery `revoke(..., terminate=True)` 强杀 worker 进程。
- 不承诺取消已经发送到 provider 的 HTTP 请求或追回已经产生的 token 费用。
- 不重写 LangGraph 执行引擎。
- 不改变 `queued`、`dispatching`、`succeeded`、`failed` 的现有取消语义。

## 推荐方案

采用方案 B：DB 驱动的协作式取消 + stream/chunk 检查 + 翻译任务阻断。

核心思路：

```text
POST /runs/{id}/cancel
  -> running run 标记为 cancelling
  -> worker 内 token 读取 DB 状态
  -> graph node 前后检查 token
  -> stream chunk 边界检查 token
  -> 检查到 cancelling/cancelled 后抛 AnalysisCancelled
  -> worker 标记 run 为 cancelled
  -> 不保存 result，不补投翻译
```

## 状态语义

```text
queued      -> cancelled
dispatching -> cancelled
running     -> cancelling -> cancelled
```

- `queued`：任务未进入 worker，直接终止。
- `dispatching`：任务处于派发阶段，直接终止并 revoke 已知 Celery task。
- `running`：用户已请求取消，worker 可能正在某个 graph node 或 provider 调用中。
- `cancelling`：中间态，表示 worker 应尽快停止。
- `cancelled`：终态，不允许写入 result 或后续 artifacts。

`AnalysisCancelled` 是正常控制流，不是失败，不产生 `run_failed`。

## 模块设计

### `tradingagents/worker/cancellation.py`

保留现有 `CancellationToken` 和 `AnalysisCancelled`。

新增 DB token helper：

```python
build_db_cancellation_token(session_factory, run_id: str) -> CancellationToken
```

token 每次检查都使用短生命周期 session 读取 `analysis_runs.status`。不复用 worker 主 session，避免 SQLAlchemy identity map 返回旧状态。

检查规则：

- status in `{"cancelling", "cancelled"}` -> cancelled。
- run 不存在 -> cancelled，避免孤儿任务继续执行。
- DB 短暂读取失败 -> 记录 warning，返回未取消。一次 DB 抖动不应误杀正常任务。

### `tradingagents/worker/analysis.py`

`run_tradingagents_analysis(...)` 增加可选参数：

```python
context: RunContext | None = None
```

构造 graph 时传入：

```python
graph = TradingAgentsGraph(
    selected_analysts=analysts,
    config=config,
    context=context,
)
```

已有 `TradingAgentsGraph.__init__` 会把 `context.cancellation_token` 传给 `GraphSetup`。

### `tradingagents/worker/jobs.py`

`execute_analysis_run()` 在 run 成功进入 `running` 后创建 `RunContext`：

```python
context = RunContext(
    run_id=run_id,
    user_id=run.user_id,
    memory_store=AnalysisMemoryRepository(repo.session),
    cancellation_token=build_db_cancellation_token(SessionLocal, run_id),
)
```

`_execute_with_optional_run_id()` 扩展签名探测：如果 executor 支持 `context` 或 `**kwargs`，传入 context；否则保持兼容旧测试桩。

`execute_analysis_run()` 捕获 `AnalysisCancelled` 后：

- rollback 当前事务。
- `repo.mark_cancelled(run_id, "analysis cancelled")`。
- commit。
- 不重新抛出，避免 Celery 把正常取消记录成 task failure 或触发重试。

### `tradingagents/graph/setup.py`

现有 `_cancellable()` 保持为主要 graph node 检查点：

```python
self.cancellation_token.raise_if_cancelled()
result = fn(state)
self.cancellation_token.raise_if_cancelled()
```

这会保证取消发生在 node 前时 node 不执行；取消发生在 node 内当前 provider 请求期间时，node 返回后立即停止后续节点。

### `tradingagents/graph/trading_graph.py`

在 `on_section_ready` 的 stream 分支增加检查点：

- stream 开始前检查一次。
- 每个 chunk 处理后检查一次。
- 调用 `on_section_ready(section, text)` 前检查一次。

这样取消后不会继续把新 section 交给翻译投递逻辑。

### 翻译任务阻断

`run_analysis_task()` 构造的 `on_section` callback 在 `translate_section_task.apply_async(...)` 前检查 run 状态：

- status in `{"cancelling", "cancelled"}` -> 不投递。
- status 仍是 `running` -> 投递。

成功后的 backfill 保持现有条件：只有 run 最终 `succeeded` 才遍历 result reports 并补投。因此取消 run 不会发生补投。

## 错误处理

- `AnalysisCancelled`：正常取消路径，最终状态为 `cancelled`。
- token DB 查询失败：记录 warning，本次检查按未取消处理，下个节点边界继续检查。
- run 缺失：按已取消处理，停止执行。
- executor 不支持 `context`：不传 context，保持兼容；生产默认 executor 支持 context 后才具备协作式取消能力。
- 取消到达时当前 LLM 请求仍在执行：等待返回或 timeout，返回后停止后续节点。

## 用户可见行为

- 点击取消后，前端先看到 `cancelling`。
- worker 在当前 graph node 边界停止后，状态变为 `cancelled`。
- 不展示成功结果。
- 如果取消发生得足够早，后续 agent 不会继续产生进度和报告。
- 如果取消发生在一个长 LLM 请求中，仍可能等待这个请求返回或超时。

## 测试计划

### Unit

- `build_db_cancellation_token` 能读取另一个 session 写入的 `cancelling` 状态并抛 `AnalysisCancelled`。
- run 不存在时 token 视为取消。
- DB 查询异常时 token 不误杀，并记录 warning。
- `_execute_with_optional_run_id` 对支持 `context` 的 executor 传入 context。
- `_execute_with_optional_run_id` 对旧 executor 不传 context，保持兼容。

### Worker

- executor 在收到 context 后调用 `context.cancellation_token.raise_if_cancelled()`，当 run 被标记为 `cancelling` 时，`execute_analysis_run()` 最终把 run 标记为 `cancelled`。
- `AnalysisCancelled` 不写入 `AnalysisRunResult`。
- `AnalysisCancelled` 不产生 `run_failed` 事件。
- cancellation 后不调用 result/artifact 写入路径。
- cancellation 后 `on_section` 不投递 `translate_section_task`。

### Graph

- node 执行前 token 已取消：node 不执行。
- node 执行后 token 变为取消：当前 node 完成，后续节点不执行。
- stream 分支在 chunk 边界检查 token。
- stream 分支在 `on_section_ready` 前检查 token。

### Regression

- 正常成功 run 仍写入 result、artifacts，并保留翻译 backfill 行为。
- `queued` / `dispatching` / terminal run 的取消 API 行为不变。

## 验收标准

- 运行中的分析任务取消后，最多执行完当前 graph node，不进入下一个 node。
- run 最终状态是 `cancelled`。
- 不生成 `analysis_run_results` 行。
- 不继续投递新的 `translate_section_task`。
- API cancel 响应格式不变。
- 现有 worker、API、graph 相关测试通过。

## 后续可选增强

- 为 provider 调用设置更短、可配置的 timeout，减少单个节点内等待时间。
- 增加管理员级 `TRADINGAGENTS_CANCEL_TERMINATE=true` 强杀开关，但不作为默认路径。
- 在 UI 上展示“正在停止当前步骤”，让用户理解当前 provider 请求可能仍需短暂等待。
