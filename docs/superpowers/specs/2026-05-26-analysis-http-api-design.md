# TradingAgents 分析 HTTP API 设计

日期：2026-05-26

分支：`phase/6-login-page`

## 目标

把 TradingAgents 的核心多智能体分析引擎包装成一个可部署的 HTTP 服务，让外部客户端可以通过 HTTP 提交分析任务、查询状态、订阅进度事件，并获取最终分析报告。

第一版只暴露分析能力。不暴露自动交易、Broker 访问、组合变更、下单或账户管理能力。

## 已确认决策

- 服务形态：异步任务式 API。
- HTTP 框架：FastAPI。
- 任务执行器：Celery。
- 队列与 Celery result backend：Redis。
- 持久化业务存储：PostgreSQL。
- 实时进度：Server-Sent Events。
- 应用层鉴权：第一版不做。
- 调用方可配置字段：只允许业务参数。
- 服务端控制配置：LLM provider、模型 ID、backend URL、cache 路径、memory 路径、数据 vendor、benchmark 设置，以及所有非业务运行配置。

## 非目标

- 不提供交易或下单 API。
- 不提供 Broker 账户 API。
- 第一版不提供 API Key、JWT 或用户账号鉴权。
- 不允许调用方传入任意 `DEFAULT_CONFIG` 覆盖项。
- 不实现超出 Celery 队列语义的多实例分布式锁。
- 第一版不做细粒度 LangGraph 节点级 streaming。

## 高层架构

```text
HTTP Client
  -> FastAPI API process
       -> PostgreSQL: runs, events, results
       -> Celery: enqueue analysis task
            -> Redis broker/result backend
            -> Celery worker process
                 -> TradingAgentsGraph.propagate()
                 -> PostgreSQL: status, events, result
```

FastAPI 进程不在请求处理函数里执行长耗时分析。它只负责请求校验、创建 run 记录、投递 Celery 任务、查询状态和结果，以及流式输出持久化事件。

Celery worker 负责执行 `TradingAgentsGraph.propagate()`。

PostgreSQL 是 run 状态、事件和结果的唯一权威数据源。Redis 只供 Celery 使用，业务状态不只存放在 Redis 中。

## API 面

### `GET /health`

返回服务健康状态。

响应结构：

```json
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok"
}
```

当前实现是轻量存活检查，返回 API 进程可响应的状态。PostgreSQL 和 Redis 的深度连通性检查留给后续增强版本或外部监控。

### `POST /runs`

创建一个异步多智能体分析任务。

请求：

```json
{
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "asset_type": "stock",
  "analysts": ["market", "social", "news", "fundamentals"]
}
```

校验规则：

- `ticker` 必填，会转成大写，长度为 1-32 个字符。
- `ticker` 只能包含字母、数字、`.`、`_`、`-` 和 `^`。
- `trade_date` 必填，格式为 `YYYY-MM-DD`。
- `trade_date` 不能晚于服务器当前日期。
- `asset_type` 只能是 `stock` 或 `crypto`。
- `analysts` 至少包含一个元素。
- 每个 analyst 只能是 `market`、`social`、`news`、`fundamentals`。
- 当 `asset_type="crypto"` 时，第一版拒绝包含 `fundamentals` 的请求，让调用方明确看到请求错误。

响应：

```json
{
  "run_id": "run_01HZ...",
  "status": "queued"
}
```

HTTP 状态码：`202 Accepted`。

副作用：

- 向 `analysis_runs` 插入一行。
- 向 `analysis_run_events` 插入 `run_queued` 事件。
- 先提交 run 记录，让 worker 的独立数据库会话一定能读取到该 run。
- 用 `run_id` 投递一个 Celery 任务。
- 把 Celery task id 写回 `analysis_runs.celery_task_id`。
- 如果投递 Celery 失败，将 run 标记为 `failed` 并记录错误。

### `GET /runs/{run_id}`

获取 run 元数据和当前状态。

响应：

```json
{
  "run_id": "run_01HZ...",
  "status": "running",
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "asset_type": "stock",
  "analysts": ["market", "news"],
  "current_step": "Analysis running",
  "created_at": "2026-05-26T13:00:00Z",
  "started_at": "2026-05-26T13:00:04Z",
  "finished_at": null,
  "error": null
}
```

状态值：

- `queued`
- `running`
- `succeeded`
- `failed`

未知 `run_id` 返回 `404`。

### `GET /runs/{run_id}/result`

获取已完成 run 的最终结果。

如果 run 尚未完成，返回 `409 Conflict`。

如果 run 已失败，返回 `409 Conflict`，并附带记录下来的错误信息。

成功响应：

```json
{
  "run_id": "run_01HZ...",
  "status": "succeeded",
  "decision": "Overweight",
  "reports": {
    "market_report": "...",
    "sentiment_report": "",
    "news_report": "...",
    "fundamentals_report": "",
    "investment_plan": "...",
    "trader_investment_plan": "...",
    "final_trade_decision": "..."
  },
  "final_state": {
    "company_of_interest": "NVDA",
    "asset_type": "stock",
    "trade_date": "2026-01-15",
    "final_trade_decision": "..."
  },
  "created_at": "2026-05-26T13:23:40Z"
}
```

`final_state` 是 LangGraph final state 的 JSON 可序列化摘要。Message 对象和其它不可序列化运行时对象会被省略，或转换成普通字符串。

### `GET /runs/{run_id}/events`

以 Server-Sent Events 形式流式返回事件。

行为：

- 返回 `text/event-stream`。
- 先发送该 run 的历史事件。
- 每 1 秒轮询 PostgreSQL，查询 `id` 大于已发送事件 id 的新事件。
- 发送新增事件。
- 发送 `succeeded` 或 `failed` 终态事件后关闭连接。
- 未知 `run_id` 返回 `404`。

示例：

```text
event: run_queued
data: {"run_id":"run_01HZ...","status":"queued"}

event: run_started
data: {"run_id":"run_01HZ...","status":"running"}

event: run_succeeded
data: {"run_id":"run_01HZ...","decision":"Overweight"}
```

第一版事件类型：

- `run_queued`
- `run_started`
- `run_succeeded`
- `run_failed`

事件模型刻意设计成可扩展。后续版本可以增加 `step_started`、`step_finished`、`tool_called` 和 `report_updated`，不需要修改 SSE endpoint 的接口契约。

## 数据库 Schema

### `analysis_runs`

```sql
CREATE TABLE analysis_runs (
    run_id text PRIMARY KEY,
    status text NOT NULL,
    ticker text NOT NULL,
    trade_date date NOT NULL,
    asset_type text NOT NULL,
    analysts jsonb NOT NULL,
    current_step text,
    celery_task_id text,
    error text,
    created_at timestamptz NOT NULL,
    started_at timestamptz,
    finished_at timestamptz
);
```

建议索引：

```sql
CREATE INDEX idx_analysis_runs_status ON analysis_runs(status);
CREATE INDEX idx_analysis_runs_created_at ON analysis_runs(created_at DESC);
CREATE INDEX idx_analysis_runs_ticker_trade_date
    ON analysis_runs(ticker, trade_date);
```

### `analysis_run_events`

```sql
CREATE TABLE analysis_run_events (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL
);
```

建议索引：

```sql
CREATE INDEX idx_analysis_run_events_run_id_id
    ON analysis_run_events(run_id, id);
CREATE INDEX idx_analysis_run_events_created_at
    ON analysis_run_events(created_at DESC);
```

### `analysis_run_results`

```sql
CREATE TABLE analysis_run_results (
    run_id text PRIMARY KEY REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    decision text NOT NULL,
    reports jsonb NOT NULL,
    final_state jsonb NOT NULL,
    created_at timestamptz NOT NULL
);
```

## Worker 行为

Celery task 签名：

```python
run_analysis_task(run_id: str) -> None
```

任务流程：

1. 通过条件更新 `WHERE status = 'queued'` 原子领取 run。
2. 如果 run 不存在或已不是 `queued`，直接返回，避免重复执行。
3. 将状态设置为 `running`。
4. 设置 `started_at`。
5. 将 `current_step` 设置为 `Analysis running`。
6. 插入 `run_started` 事件。
7. 从 `DEFAULT_CONFIG` 深拷贝构建服务端配置，避免不同 worker 任务共享嵌套配置对象。
8. 创建 `TradingAgentsGraph(selected_analysts=run.analysts, config=config)`。
9. 执行 `graph.propagate(run.ticker, run.trade_date, asset_type=run.asset_type)`。
10. 抽取 `decision`、`reports` 和 JSON-safe `final_state`。
11. 插入 `analysis_run_results`。
12. 将状态设置为 `succeeded`。
13. 设置 `finished_at`。
14. 将 `current_step` 设置为 `Completed`。
15. 插入 `run_succeeded` 事件。

失败流程：

1. 捕获异常。
2. 将简短错误信息写入 `analysis_runs.error`。
3. 将状态设置为 `failed`。
4. 设置 `finished_at`。
5. 将 `current_step` 设置为 `Failed`。
6. 插入带 error payload 的 `run_failed` 事件。
7. 只有当 implementation plan 明确配置 Celery retry 行为时，才重新抛出异常。

第一版默认不实现自动重试。LLM-heavy 任务重跑成本高，也可能重复调用外部 provider。运维或调用方可以显式提交新的 run。

## 配置

环境变量：

- `DATABASE_URL`：PostgreSQL 连接字符串。
- `REDIS_URL`：Redis 连接字符串，用于 Celery broker 和 result backend。
- `TRADINGAGENTS_API_TASK_TIME_LIMIT_SECONDS`：Celery hard time limit，默认 `3600`。
- `TRADINGAGENTS_API_WORKER_CONCURRENCY`：文档化的部署参数，推荐默认值为 `1`。

现有 TradingAgents 环境变量仍由服务端控制：

- `TRADINGAGENTS_LLM_PROVIDER`
- `TRADINGAGENTS_DEEP_THINK_LLM`
- `TRADINGAGENTS_QUICK_THINK_LLM`
- `TRADINGAGENTS_LLM_BACKEND_URL`
- `TRADINGAGENTS_OUTPUT_LANGUAGE`
- `TRADINGAGENTS_MAX_DEBATE_ROUNDS`
- `TRADINGAGENTS_MAX_RISK_ROUNDS`
- `TRADINGAGENTS_CHECKPOINT_ENABLED`
- `TRADINGAGENTS_RESULTS_DIR`
- `TRADINGAGENTS_CACHE_DIR`
- `TRADINGAGENTS_MEMORY_LOG_PATH`

Provider API keys 也仍由服务端控制。客户端不能在请求 payload 中传 provider key。

## 部署命令

API 进程：

```bash
uvicorn tradingagents.api.app:app --host 0.0.0.0 --port 8000
```

Worker 进程：

```bash
celery -A tradingagents.worker.celery_app worker --loglevel=info --concurrency=1
```

必需服务：

- PostgreSQL，可通过 `DATABASE_URL` 访问。
- Redis，可通过 `REDIS_URL` 访问。

## 包依赖

实现需要新增依赖：

- `fastapi`
- `uvicorn`
- `celery`
- `sqlalchemy`
- `psycopg[binary]` 或 `psycopg2-binary`
- `sse-starlette` 或原生 `StreamingResponse`

在保持实现清晰的前提下，使用最小依赖集。如果 FastAPI 原生 `StreamingResponse` 足够实现 SSE，就不要额外加入 `sse-starlette`。

如果 setuptools 当前没有包含新包，实现时需要把 `tradingagents.api*` 和 `tradingagents.worker*` 纳入 package discovery。

## 错误处理

请求结构校验错误返回 FastAPI 默认 `422` 响应。

领域校验错误返回 `400`，例如：

- crypto 请求包含 `fundamentals`。
- analyst key 不支持。
- trade date 是未来日期。
- ticker 字符非法。

未知 run 返回 `404`。

结果在完成前被请求时返回 `409`。

失败 run 的 result 请求返回 `409`，并附带已记录的失败信息。

Worker 异常会在 task 退出前持久化到 PostgreSQL。

## 测试策略

实现必须 test-first。

最低测试覆盖：

- 请求校验接受合法分析请求。
- 请求校验拒绝非法 ticker。
- 请求校验拒绝未来日期。
- 请求校验拒绝 crypto fundamentals。
- `POST /runs` 插入 run 和 queued event，并投递 Celery 任务。
- `GET /runs/{run_id}` 返回持久化 run 元数据。
- `GET /runs/{run_id}/result` 在任务完成前返回 `409`。
- `GET /runs/{run_id}/result` 在任务完成后返回存储结果。
- Worker 成功路径写入 result 和 `run_succeeded`。
- Worker 失败路径写入失败状态和 `run_failed`。
- SSE endpoint 按顺序发送历史事件。

测试不能调用真实 LLM 或市场数据 provider。Worker 测试应 patch `TradingAgentsGraph`，或注入 fake analysis executor。

## 安全与运维说明

由于第一版不做应用层鉴权，生产部署必须放在以下任一保护层之后：

- 私有网络；
- 防火墙 allowlist；
- 带鉴权的反向代理；
- API gateway；
- VPN。

不要把原始服务端口直接暴露到公网。

Celery worker 并发要保守设置。每次分析可能触发大量外部 LLM 和市场数据调用。第一版推荐部署为一个 API 进程加一个 worker 进程，并设置 `--concurrency=1`。

## 第一版之后的后续事项

- 增加 API key 鉴权。
- 增加取消任务 endpoint。
- 为 `POST /runs` 增加 idempotency key。
- 通过 streaming worker chunks 增加细粒度 LangGraph 进度事件。
- 增加旧 runs、results、events 的保留策略。
- 增加失败 run 检查用 admin endpoint。
- 增加包含 API、worker、PostgreSQL 和 Redis 的 Docker Compose profile。
