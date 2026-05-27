# Analysis Concurrency And Capacity Design

Date: 2026-05-28

Branch: `phase/8-increase-concurrency-for-analysis-functions`

## Goal

Upgrade the analysis service from a single-worker queue into a multi-user task
system that can safely support:

- 5 concurrent running analysis runs per user.
- 100 concurrent running analysis runs across the whole system.
- Queued overflow instead of rejecting normal bursts.
- Fair dispatch so one heavy user cannot starve other users.
- Run-level isolation for reports, checkpoints, final state, progress, and
  memory side effects.
- Cooperative cancellation and worker crash recovery.

## Non-Goals

- This design does not increase provider limits by itself. LLM and data vendor
  limits still depend on account quotas and must be configured explicitly.
- This design does not make every LangGraph node internally parallel. Run-level
  concurrency is the priority; run-internal analyst concurrency remains a
  separate setting.
- This design does not rely on killing worker processes for cancellation.
  Process termination may exist as an admin emergency action, but normal cancel
  is cooperative.

## Core Decision

`POST /runs` must only create a queued run. It must not enqueue Celery directly.

A dedicated dispatcher owns the transition from `queued` to executable work:

```text
POST /runs
  -> analysis_runs(status=queued)
  -> dispatcher checks capacity and fairness
  -> status=dispatching
  -> enqueue Celery task
  -> worker sets status=running
```

This is the key change that makes per-user and global capacity enforceable.

## Target Capacity

Configuration defaults:

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

The system-level target of 100 running analyses is reached by horizontal worker
capacity, for example 10 worker replicas with concurrency 10. Smaller
deployments can keep the same logic but run fewer workers.

## State Machine

```text
queued
  -> dispatching
  -> running
  -> succeeded

queued
  -> cancelled

dispatching
  -> running
  -> queued      # enqueue failed or dispatch lease expired
  -> cancelled

running
  -> cancelling
  -> cancelled
  -> failed
  -> succeeded

running
  -> queued      # retryable worker loss before max attempts
```

State meanings:

- `queued`: accepted and waiting for capacity.
- `dispatching`: capacity lease acquired; dispatcher is enqueueing work.
- `running`: worker has started and is heartbeating.
- `cancelling`: user requested cancellation while worker may still be inside a
  graph node or provider call.
- `cancelled`: cancellation completed; no result should be written.
- `succeeded`: final result and artifacts are available.
- `failed`: terminal failure after non-retryable error or exhausted retries.

## Database Changes

Extend `analysis_runs`:

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

Add `analysis_run_artifacts`:

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

Add `analysis_memory_entries`:

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

Indexes:

```text
analysis_runs(status, priority desc, created_at)
analysis_runs(user_id, status)
analysis_runs(heartbeat_at)
analysis_run_artifacts(run_id, kind)
analysis_memory_entries(user_id, ticker, pending, created_at desc)
```

## Capacity Enforcement

Capacity is enforced at dispatch time, not at run creation time.

Creation rule:

```text
if user queued + dispatching + running >= MAX_QUEUED_PER_USER + MAX_RUNNING_PER_USER:
  return 429
else:
  create queued run
```

Dispatch rule:

```text
if system running + dispatching >= MAX_RUNNING_SYSTEM:
  stop dispatch loop

if user running + dispatching >= MAX_RUNNING_PER_USER:
  skip this user's queued run

else:
  acquire dispatch lease and enqueue
```

`dispatching` counts against capacity because a task has already been selected
and may start at any moment.

## Fair Dispatcher

The dispatcher runs every `TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS`.

It must avoid strict FIFO across all runs because one user can submit many runs
and starve later users. The dispatcher uses user-round-robin:

```text
1. select users with queued runs ordered by oldest queued run
2. for each user, dispatch at most one run per dispatcher pass
3. repeat on the next pass while global capacity remains
```

PostgreSQL selection must use row locks:

```sql
SELECT ...
FROM analysis_runs
WHERE status = 'queued'
ORDER BY priority DESC, created_at ASC
FOR UPDATE SKIP LOCKED
```

Multiple dispatcher instances are allowed, but one instance is enough for the
initial deployment. `SKIP LOCKED` keeps behavior safe if more are added.

## Celery Worker Configuration

Celery configuration:

```python
worker_prefetch_multiplier = 1
task_acks_late = True
task_reject_on_worker_lost = True
task_time_limit = 3600
task_soft_time_limit = 3300
```

Worker command:

```bash
celery -A tradingagents.worker.celery_app worker \
  --loglevel=info \
  --concurrency="${TRADINGAGENTS_WORKER_CONCURRENCY:-10}"
```

`worker_prefetch_multiplier=1` is required. Without it, a worker can reserve too
many long-running runs and make queue latency unfair.

## Worker Execution Contract

Worker flow:

```text
1. load run by run_id
2. verify status is dispatching or running
3. set status=running, started_at if missing, heartbeat_at=now
4. start heartbeat loop
5. create RunContext
6. run graph with cancellation token and provider limiter
7. write artifacts, result, memory entry
8. set status=succeeded
9. emit run_succeeded
```

Failure flow:

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

The worker must update `heartbeat_at` every
`TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS` while the task is active.

## Sweeper

The sweeper runs periodically and repairs stale runs:

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

The sweeper emits `run_requeued`, `run_failed`, or `run_cancelled` events so the
UI sees a consistent state transition.

## RunContext

Graph execution receives a single context object:

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

All side effects must use this context. Graph code must not write to shared
global report, checkpoint, result, or memory paths.

## Artifact Isolation

All artifacts are keyed by `run_id`.

Local storage layout:

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

Report paths may include ticker/date for readability, but uniqueness must come
from `run_id`, not timestamp or ticker.

`analysis_run_artifacts` stores metadata for every persisted artifact. API
responses should serve artifacts by `artifact_id`, scoped by run ownership.

## Checkpoints

Checkpoint namespace changes from ticker/date to run_id:

```text
thread_id = run_id
checkpoint_db = artifacts/run_id/checkpoints/graph.sqlite
```

This prevents same ticker and same date runs from sharing state.

On cancellation:

```text
delete artifacts/run_id/checkpoints/
```

On success:

```text
delete checkpoint rows or remove checkpoint artifact
```

## DB Memory Store

The markdown memory file is replaced by `analysis_memory_entries`.

Past context query:

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker = :ticker
  AND pending = false
ORDER BY created_at DESC
LIMIT 5;
```

Cross-ticker lessons:

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker != :ticker
  AND pending = false
ORDER BY created_at DESC
LIMIT 3;
```

Pending reflection resolution must lock rows:

```sql
SELECT *
FROM analysis_memory_entries
WHERE user_id = :user_id
  AND ticker = :ticker
  AND pending = true
FOR UPDATE SKIP LOCKED;
```

This prevents two concurrent same-ticker runs from resolving the same pending
memory entry twice.

## Provider Limits

System run concurrency does not equal provider call concurrency.

Redis limiters protect provider calls:

```text
llm:{provider}:concurrent
llm:{provider}:requests_per_minute
llm:{provider}:tokens_per_minute
data:{vendor}:concurrent
data:{vendor}:requests_per_minute
user:{user_id}:llm_concurrent
```

Before an LLM or data vendor call, execution acquires a limiter permit. If no
permit is available, the call waits up to a configured timeout. If the timeout
expires, the run records a retryable provider-capacity error and may return to
`queued`.

This allows 100 runs to be `running` without allowing 100 or more provider calls
to hit the same vendor at once.

## Cooperative Cancellation

Cancel API behavior:

```text
queued      -> cancelled
dispatching -> cancelling
running     -> cancelling
```

It also writes a Redis flag:

```text
cancel:{run_id}=1
```

The graph checks `CancellationToken.raise_if_cancelled()`:

- before graph start
- before each LangGraph node
- after each LangGraph node
- before each tool call
- before each LLM call
- before saving artifacts
- before writing result
- before writing memory

`AnalysisCancelled` is not a failure. Worker catches it and marks the run
`cancelled`.

LLM HTTP calls cannot always be interrupted mid-request, so provider clients
must have explicit timeouts.

## Progress Events

The event model should expose user-readable phases:

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

`run_progress` payload:

```json
{
  "phase": "analyst_market",
  "label": "行情分析",
  "percent": 25,
  "message": "正在分析价格走势和技术指标"
}
```

Required phases:

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

## SSE Scaling

The current polling-based SSE stream is acceptable for low volume, but for 100
running runs and many viewers it should not query PostgreSQL once per second per
connection.

Target implementation:

```text
worker writes event to DB
worker publishes event to Redis pub/sub channel run:{run_id}
SSE endpoint streams Redis pub/sub messages
on reconnect, API replays missed DB events by last event id
```

This keeps PostgreSQL as the durable event store and Redis as the live fanout
path.

## API Changes

`POST /runs` response:

```json
{
  "run_id": "run_...",
  "status": "queued",
  "queue_position": 8
}
```

When user backlog is too large:

```http
429 Too Many Requests
```

```json
{
  "detail": "too many queued analysis runs"
}
```

New endpoints:

```text
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/artifacts/{artifact_id}
GET /admin/capacity
```

`GET /admin/capacity`:

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

## Deployment Shape

Small deployment:

```text
api replicas: 1
dispatcher replicas: 1
worker replicas: 2
worker concurrency: 5
effective worker capacity: 10
max_running_system: 10
```

Target deployment:

```text
api replicas: 2
dispatcher replicas: 1-2
worker replicas: 10
worker concurrency: 10
effective worker capacity: 100
max_running_system: 100
```

Redis and PostgreSQL must be managed services or provisioned with enough
connections and memory for the target capacity.

## Testing Requirements

Automated tests must cover:

- A user can create runs beyond the running limit and they remain queued.
- Dispatcher starts at most 5 runs for a single user.
- Dispatcher starts at most 100 runs globally.
- Dispatcher is fair across users.
- Same ticker and same date can run concurrently without artifact, checkpoint,
  or result collisions.
- Running cancellation transitions to `cancelling` then `cancelled`.
- Cancelled runs do not write result or memory entries.
- Stale `dispatching` runs return to `queued`.
- Stale `running` runs are requeued or failed according to attempt count.
- Provider limiter delays or requeues work instead of letting provider calls
  stampede.
- SSE streams replay missed events and live-stream Redis events without mixing
  run ids.
- DB memory pending resolution is not duplicated by concurrent same-ticker runs.

## Migration Plan

1. Add schema fields and new tables.
2. Add capacity config and repository methods.
3. Change `POST /runs` to create queued runs only.
4. Add dispatcher and tests for per-user/global capacity.
5. Add worker heartbeat and sweeper.
6. Add run_id artifact store and migrate report/final-state writes.
7. Replace markdown memory with DB memory store.
8. Change checkpoint namespace to run_id.
9. Add provider limiter.
10. Add cooperative cancellation checks.
11. Switch SSE live delivery to Redis pub/sub with DB replay.
12. Update frontend queue position, progress, cancellation, and artifacts views.

Each step should be independently tested and committed.

## Open Operational Assumptions

- Provider quotas must be configured per deployment. The application enforces
  configured limits but cannot infer account-level RPM/TPM accurately.
- 100 running analyses requires enough worker CPU, memory, Redis capacity,
  PostgreSQL connections, and provider quota. If any layer is lower, the
  dispatcher limit must be set lower.
- `MAX_RUNNING_SYSTEM` should not exceed effective worker capacity by a large
  margin, or many runs will appear running while waiting inside workers.
