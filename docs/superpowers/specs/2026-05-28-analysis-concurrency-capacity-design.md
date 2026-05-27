# 分析任务并发与容量设计

日期：2026-05-28

分支：`phase/8-increase-concurrency-for-analysis-functions`

## 目标

把分析服务从单 worker 队列升级成面向多用户的任务系统，安全支持：

- 单用户最多 5 个 `running` 分析任务。
- 全系统最多 100 个 `running` 分析任务。
- 超出容量的任务进入 `queued`，不因为正常突发直接拒绝。
- 公平派发，避免一个重度用户饿死其他用户。
- 每个 run 的 reports、checkpoint、final state、progress、memory 副作用完全隔离。
- 支持协作式取消和 worker 崩溃恢复。

## 非目标

- 本设计不会自动提升 LLM provider 或数据供应商额度。LLM 和数据接口限制仍取决于账号配额，必须按部署环境显式配置。
- 本设计不要求每个 LangGraph node 内部并行。优先解决 run 级并发；单个 run 内 analyst 并发仍由独立配置控制。
- 本设计不依赖强杀 worker 进程来取消任务。强杀可以作为管理员紧急能力存在，但普通取消必须是协作式取消。

## 核心决策

`POST /runs` 只负责创建 `queued` run，不再直接投递 Celery 任务。

新增独立 dispatcher，统一负责从 `queued` 到可执行任务的状态转换：

```text
POST /runs
  -> analysis_runs(status=queued)
  -> dispatcher 检查容量和公平性
  -> status=dispatching
  -> enqueue Celery task
  -> worker 设置 status=running
```

这是能可靠执行“单用户 5 个、全系统 100 个”容量规则的关键变化。

## 目标容量

默认配置：

```env
TRADINGAGENTS_MAX_RUNNING_SYSTEM=100
TRADINGAGENTS_MAX_RUNNING_PER_USER=5
TRADINGAGENTS_MAX_QUEUED_PER_USER=50
TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS=1
TRADINGAGENTS_RUN_LEASE_SECONDS=600
TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS=10
TRADINGAGENTS_WORKER_STALE_AFTER_SECONDS=90
TRADINGAGENTS_WORKER_CONCURRENCY=10
TRADINGAGENTS_WORKER_REPLICAS=10
```

全系统 100 个 running 分析通过横向 worker 容量实现。例如 10 个 worker 副本，每个 worker `concurrency=10`。小规模部署可以保留同一套逻辑，但减少 worker 数量和 `MAX_RUNNING_SYSTEM`。

## 状态机

```text
queued
  -> dispatching
  -> running
  -> succeeded

queued
  -> cancelled

dispatching
  -> running
  -> queued      # enqueue 失败或 dispatch lease 过期
  -> cancelled

running
  -> cancelling
  -> cancelled
  -> failed
  -> succeeded

running
  -> queued      # worker 丢失且未超过最大重试次数
```

状态含义：

- `queued`：任务已接受，正在等待容量。
- `dispatching`：已经获取容量 lease，dispatcher 正在投递任务。
- `running`：worker 已开始执行，并持续 heartbeat。
- `cancelling`：用户已请求取消，但 worker 可能仍在某个 graph node 或 provider 调用中。
- `cancelled`：取消完成，不应写入 result。
- `succeeded`：最终结果和 artifacts 可用。
- `failed`：不可重试错误或重试耗尽后的终态失败。

## 数据库变更

扩展 `analysis_runs`：

```text
priority integer not null default 0
attempt_count integer not null default 0
max_attempts integer not null default 2
current_phase text null
progress_percent integer null
dispatched_at timestamptz null
heartbeat_at timestamptz null
lease_expires_at timestamptz null
updated_at timestamptz not null
```

新增 `analysis_run_artifacts`：

```text
artifact_id text primary key
run_id text not null references analysis_runs(run_id) on delete cascade
kind text not null              -- report_md, final_state_json, checkpoint, log
storage_backend text not null   -- local, s3, minio
storage_key text not null
content_type text not null
size_bytes bigint not null
sha256 text not null
created_at timestamptz not null
```

新增 `analysis_memory_entries`：

```text
id bigserial primary key
user_id text not null references users(user_id) on delete cascade
run_id text not null references analysis_runs(run_id) on delete cascade
ticker text not null
trade_date date not null
rating text not null
decision_markdown text not null
pending boolean not null
raw_return double precision null
alpha_return double precision null
holding_days integer null
reflection text null
created_at timestamptz not null
resolved_at timestamptz null
```

索引：

```text
analysis_runs(status, priority desc, created_at)
analysis_runs(user_id, status)
analysis_runs(heartbeat_at)
analysis_run_artifacts(run_id, kind)
analysis_memory_entries(user_id, ticker, pending, created_at desc)
```

## 容量控制

容量在 dispatch 阶段控制，而不是在创建 run 时控制。

创建规则：

```text
if user queued + dispatching + running >= MAX_QUEUED_PER_USER + MAX_RUNNING_PER_USER:
  return 429
else:
  create queued run
```

派发规则：

```text
if system running + dispatching >= MAX_RUNNING_SYSTEM:
  stop dispatch loop

if user running + dispatching >= MAX_RUNNING_PER_USER:
  skip this user's queued run

else:
  acquire dispatch lease and enqueue
```

`dispatching` 计入容量，因为任务已经被选中，随时可能进入执行。

## 公平 Dispatcher

dispatcher 每 `TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS` 运行一次。

不能对所有 run 做严格 FIFO，因为一个用户可以先提交大量任务，让后来的其他用户长期排不到。dispatcher 采用按用户轮询的公平策略：

```text
1. 选择拥有 queued run 的用户，按该用户最早 queued run 排序
2. 每轮每个用户最多派发 1 个 run
3. 下一轮继续派发，直到全局容量耗尽
```

PostgreSQL 选择任务时必须使用行锁：

```sql
SELECT ...
FROM analysis_runs
WHERE status = 'queued'
ORDER BY priority DESC, created_at ASC
FOR UPDATE SKIP LOCKED
```

初始部署一个 dispatcher 实例即可。后续即使部署多个 dispatcher，`SKIP LOCKED` 也能避免多个实例抢同一个 run。

## Celery Worker 配置

Celery 配置：

```python
worker_prefetch_multiplier = 1
task_acks_late = True
task_reject_on_worker_lost = True
task_time_limit = 3600
task_soft_time_limit = 3300
```

worker 启动命令：

```bash
celery -A tradingagents.worker.celery_app worker \
  --loglevel=info \
  --concurrency="${TRADINGAGENTS_WORKER_CONCURRENCY:-10}"
```

`worker_prefetch_multiplier=1` 是必需项。否则某个 worker 会预取过多长任务，造成队列延迟和用户公平性变差。

## Worker 执行契约

worker 执行流程：

```text
1. 按 run_id 加载 run
2. 确认 status 是 dispatching 或 running
3. 设置 status=running；如果 started_at 为空则写入 started_at；写 heartbeat_at=now
4. 启动 heartbeat loop
5. 创建 RunContext
6. 使用 cancellation token 和 provider limiter 执行 graph
7. 写 artifacts、result、memory entry
8. 设置 status=succeeded
9. 发出 run_succeeded 事件
```

失败流程：

```text
retryable provider/network error:
  attempt_count += 1
  if attempt_count < max_attempts:
    status=queued
  else:
    status=failed

non-retryable model config error:
  status=failed

AnalysisCancelled:
  status=cancelled
  no result
  no memory write
  cleanup checkpoint
```

worker 在任务 active 期间必须每 `TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS` 更新一次 `heartbeat_at`。

## Sweeper

sweeper 周期性运行，用来修复卡住的 run：

```text
dispatching where lease_expires_at < now:
  status=queued
  clear celery_task_id

running/cancelling where heartbeat_at < now - STALE_AFTER:
  if attempt_count < max_attempts and status != cancelling:
    status=queued
  else:
    status=failed or cancelled
```

sweeper 需要发出 `run_requeued`、`run_failed` 或 `run_cancelled` 事件，让 UI 看到一致的状态变化。

## RunContext

graph 执行时接收一个统一上下文对象：

```text
RunContext
- run_id
- user_id
- ticker
- trade_date
- artifact_store
- memory_store
- progress_reporter
- cancellation_token
- provider_limiter
- checkpoint_namespace
```

所有副作用都必须通过 `RunContext` 完成。graph 代码不能再写共享的全局 report、checkpoint、result 或 memory 路径。

## Artifact 隔离

所有 artifacts 都以 `run_id` 作为隔离键。

本地存储布局：

```text
artifacts/
  run_<id>/
    reports/
      complete_report.md
      1_analysts/market.md
      2_research/manager.md
      3_trading/trader.md
      5_portfolio/decision.md
    state/
      final_state.json
    checkpoints/
      graph.sqlite
```

report 路径可以带 ticker/date 方便阅读，但唯一性必须来自 `run_id`，不能依赖 timestamp 或 ticker。

`analysis_run_artifacts` 保存每个持久化 artifact 的元数据。API 按 `artifact_id` 提供下载，并且必须按 run ownership 做权限限制。

## Checkpoint

checkpoint namespace 从 ticker/date 改为 run_id：

```text
thread_id = run_id
checkpoint_db = artifacts/run_id/checkpoints/graph.sqlite
```

这样同 ticker、同日期的并发 run 不会共享状态。

取消时：

```text
delete artifacts/run_id/checkpoints/
```

成功时：

```text
delete checkpoint rows or remove checkpoint artifact
```

## DB Memory Store

用 `analysis_memory_entries` 替换 markdown memory 文件。

同 ticker 历史上下文查询：

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker = :ticker
  AND pending = false
ORDER BY created_at DESC
LIMIT 5;
```

跨 ticker lessons 查询：

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker != :ticker
  AND pending = false
ORDER BY created_at DESC
LIMIT 3;
```

pending reflection 解析必须锁行：

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker = :ticker
  AND pending = true
FOR UPDATE SKIP LOCKED;
```

这样两个同 ticker 并发 run 不会重复解析同一个 pending memory entry。

## Provider 限流

系统 run 并发不等于 provider 调用并发。

Redis limiter 负责保护 provider 调用：

```text
llm:{provider}:concurrent
llm:{provider}:requests_per_minute
llm:{provider}:tokens_per_minute
data:{vendor}:concurrent
data:{vendor}:requests_per_minute
user:{user_id}:llm_concurrent
```

每次 LLM 或数据供应商调用前，执行逻辑必须先获取 limiter permit。如果没有可用 permit，调用等待到配置的超时时间。超时后，run 记录 retryable provider-capacity error，并可回到 `queued` 重试。

这允许系统有 100 个 `running` run，但不会让 100 个以上 provider 调用同时打到同一个供应商。

## 协作式取消

取消 API 行为：

```text
queued      -> cancelled
dispatching -> cancelling
running     -> cancelling
```

同时写 Redis flag：

```text
cancel:{run_id}=1
```

graph 检查 `CancellationToken.raise_if_cancelled()` 的位置：

- graph 开始前
- 每个 LangGraph node 前
- 每个 LangGraph node 后
- 每次 tool call 前
- 每次 LLM call 前
- 保存 artifacts 前
- 写 result 前
- 写 memory 前

`AnalysisCancelled` 不是失败。worker 捕获后把 run 标记为 `cancelled`。

LLM HTTP 调用不一定能在请求中途被打断，所以 provider client 必须设置明确 timeout。

## 进度事件

事件模型需要暴露用户可读的阶段：

```text
run_queued
run_dispatching
run_started
run_progress
run_cancelling
run_cancelled
run_failed
run_succeeded
run_requeued
```

`run_progress` payload：

```json
{
  "phase": "analyst_market",
  "label": "行情分析",
  "percent": 25,
  "message": "正在分析价格走势和技术指标"
}
```

必需阶段：

```text
memory_resolving
analyst_market
analyst_news
analyst_sentiment
analyst_fundamentals
research_debate
trader_plan
risk_debate
portfolio_decision
saving_artifacts
completed
```

## SSE 扩展

当前基于轮询的 SSE stream 在低容量下可用，但 100 个 running run 和大量观看连接下，不应该让每个连接每秒查询 PostgreSQL。

目标实现：

```text
worker writes event to DB
worker publishes event to Redis pub/sub channel run:{run_id}
SSE endpoint streams Redis pub/sub messages
on reconnect, API replays missed DB events by last event id
```

PostgreSQL 保持 durable event store，Redis 只负责 live fanout。

## API 变化

`POST /runs` 响应：

```json
{
  "run_id": "run_...",
  "status": "queued",
  "queue_position": 8
}
```

当用户 backlog 过大时：

```http
429 Too Many Requests
```

```json
{
  "detail": "too many queued analysis runs"
}
```

新增端点：

```text
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/artifacts/{artifact_id}
GET /admin/capacity
```

`GET /admin/capacity`：

```json
{
  "max_running_system": 100,
  "running_system": 73,
  "queued_system": 211,
  "max_running_per_user": 5,
  "providers": {
    "openai": {
      "concurrent_in_use": 31,
      "concurrent_limit": 50
    }
  }
}
```

## 部署形态

小规模部署：

```text
api replicas: 1
dispatcher replicas: 1
worker replicas: 2
worker concurrency: 5
effective worker capacity: 10
max_running_system: 10
```

目标部署：

```text
api replicas: 2
dispatcher replicas: 1-2
worker replicas: 10
worker concurrency: 10
effective worker capacity: 100
max_running_system: 100
```

Redis 和 PostgreSQL 应使用托管服务，或至少按目标容量预留足够连接数、内存和磁盘 I/O。

## 测试要求

自动化测试必须覆盖：

- 用户可以创建超过 running limit 的 run，超出的 run 保持 queued。
- dispatcher 对单用户最多启动 5 个 run。
- dispatcher 对全系统最多启动 100 个 run。
- dispatcher 对多个用户公平派发。
- 同 ticker、同日期可以并发运行，不发生 artifact、checkpoint 或 result 覆盖。
- running 中取消会从 `cancelling` 进入 `cancelled`。
- cancelled run 不写 result，也不写 memory entry。
- 卡住的 `dispatching` run 会回到 `queued`。
- 卡住的 `running` run 会按 attempt count 重排或失败。
- provider limiter 会延迟或重排工作，不让 provider 调用形成 stampede。
- SSE 能 replay missed events，并通过 Redis live stream 发送事件，不串 run id。
- DB memory pending resolution 在同 ticker 并发 run 下不会重复处理。

## 迁移计划

1. 增加 schema 字段和新表。
2. 增加 capacity config 和 repository 方法。
3. 把 `POST /runs` 改成只创建 queued run。
4. 增加 dispatcher，并测试单用户/全局容量。
5. 增加 worker heartbeat 和 sweeper。
6. 增加 run_id artifact store，并迁移 report/final-state 写入。
7. 用 DB memory store 替换 markdown memory。
8. 把 checkpoint namespace 改成 run_id。
9. 增加 provider limiter。
10. 增加协作式取消检查。
11. 把 SSE live delivery 切换到 Redis pub/sub + DB replay。
12. 更新前端队列位置、进度、取消和 artifacts 视图。

每一步都必须独立测试并提交。

## 运行假设

- provider quota 必须按部署环境配置。应用负责执行配置好的限流，但不能准确自动推断账号级 RPM/TPM。
- 100 个 running analyses 需要足够的 worker CPU、内存、Redis 容量、PostgreSQL 连接数和 provider quota。任一层容量更低时，dispatcher limit 必须相应调低。
- `MAX_RUNNING_SYSTEM` 不应明显超过有效 worker capacity，否则大量 run 会显示为 running，但实际只是在 worker 内等待。
