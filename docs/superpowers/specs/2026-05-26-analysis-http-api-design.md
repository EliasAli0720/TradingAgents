# TradingAgents Analysis HTTP API Design

Date: 2026-05-26

Branch: `phase/6-login-page`

## Objective

Expose the core TradingAgents multi-agent analysis engine as a deployable HTTP service so external clients can submit analysis jobs, poll status, stream progress events, and fetch final reports over HTTP.

The first version only exposes analysis. It does not expose automatic trading, broker access, portfolio mutation, order placement, or account management.

## Confirmed Decisions

- Service style: asynchronous task API.
- HTTP framework: FastAPI.
- Task runner: Celery.
- Queue and Celery result backend: Redis.
- Durable business storage: PostgreSQL.
- Realtime progress: Server-Sent Events.
- Application-level authentication: none in the first version.
- Caller-configurable analysis fields: business parameters only.
- Server-controlled configuration: LLM provider, model IDs, backend URLs, cache paths, memory paths, data vendors, benchmark settings, and all non-business runtime configuration.

## Non-Goals

- No trading or order execution APIs.
- No broker account APIs.
- No API key, JWT, or user-account authentication in the first version.
- No user-supplied arbitrary `DEFAULT_CONFIG` override.
- No multi-instance distributed locking beyond Celery queue semantics.
- No fine-grained LangGraph node streaming in the first version.

## High-Level Architecture

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

The FastAPI process never performs long-running analysis inside request handlers. It validates requests, creates run records, enqueues Celery tasks, serves status and result queries, and streams durable events.

The Celery worker owns execution of `TradingAgentsGraph.propagate()`.

PostgreSQL is the source of truth for run state, events, and results. Redis is used by Celery only; business state is not stored exclusively in Redis.

## API Surface

### `GET /health`

Returns service health.

Response shape:

```json
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok"
}
```

If PostgreSQL or Redis cannot be reached, the endpoint returns a non-2xx response with details.

### `POST /runs`

Creates an asynchronous multi-agent analysis run.

Request:

```json
{
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "asset_type": "stock",
  "analysts": ["market", "social", "news", "fundamentals"]
}
```

Validation rules:

- `ticker` is required, uppercased, 1-32 characters.
- `ticker` may contain letters, digits, `.`, `_`, `-`, and `^`.
- `trade_date` is required in `YYYY-MM-DD` format.
- `trade_date` cannot be in the future relative to server date.
- `asset_type` is either `stock` or `crypto`.
- `analysts` contains at least one item.
- Each analyst is one of `market`, `social`, `news`, `fundamentals`.
- For `asset_type="crypto"`, `fundamentals` is rejected in the first version so callers see a clear request error.

Response:

```json
{
  "run_id": "run_01HZ...",
  "status": "queued"
}
```

HTTP status: `202 Accepted`.

Side effects:

- Insert one row into `analysis_runs`.
- Insert `run_queued` event into `analysis_run_events`.
- Enqueue one Celery task with `run_id`.
- Save Celery task id back to `analysis_runs.celery_task_id`.

### `GET /runs/{run_id}`

Fetches run metadata and current status.

Response:

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

Status values:

- `queued`
- `running`
- `succeeded`
- `failed`

Unknown `run_id` returns `404`.

### `GET /runs/{run_id}/result`

Fetches final result for a completed run.

If the run is not complete, returns `409 Conflict`.

If the run failed, returns `409 Conflict` with the recorded error.

Successful response:

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

The `final_state` value is a JSON-serializable summary of the LangGraph final state. Message objects and other non-serializable runtime objects are omitted or converted to plain strings.

### `GET /runs/{run_id}/events`

Streams events as Server-Sent Events.

Behavior:

- Returns `text/event-stream`.
- Sends historical events for the run first.
- Polls PostgreSQL every second for events with `id` greater than the last sent id.
- Sends newly inserted events.
- Closes after sending a terminal event for `succeeded` or `failed`.
- Unknown `run_id` returns `404`.

Example:

```text
event: run_queued
data: {"run_id":"run_01HZ...","status":"queued"}

event: run_started
data: {"run_id":"run_01HZ...","status":"running"}

event: run_succeeded
data: {"run_id":"run_01HZ...","decision":"Overweight"}
```

First-version event types:

- `run_queued`
- `run_started`
- `run_succeeded`
- `run_failed`

The event model is intentionally extensible. Later versions can add `step_started`, `step_finished`, `tool_called`, and `report_updated` without changing the SSE endpoint contract.

## Database Schema

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

Recommended indexes:

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

Recommended indexes:

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

## Worker Behavior

Celery task signature:

```python
run_analysis_task(run_id: str) -> None
```

Task flow:

1. Load run from PostgreSQL.
2. If run status is not `queued`, return without doing work.
3. Set status to `running`.
4. Set `started_at`.
5. Set `current_step` to `Analysis running`.
6. Insert `run_started` event.
7. Build server-side config from `DEFAULT_CONFIG.copy()`.
8. Instantiate `TradingAgentsGraph(selected_analysts=run.analysts, config=config)`.
9. Execute `graph.propagate(run.ticker, run.trade_date, asset_type=run.asset_type)`.
10. Extract `decision`, `reports`, and JSON-safe `final_state`.
11. Insert `analysis_run_results`.
12. Set status to `succeeded`.
13. Set `finished_at`.
14. Set `current_step` to `Completed`.
15. Insert `run_succeeded` event.

Failure flow:

1. Catch exception.
2. Store a concise error string in `analysis_runs.error`.
3. Set status to `failed`.
4. Set `finished_at`.
5. Set `current_step` to `Failed`.
6. Insert `run_failed` event with error payload.
7. Re-raise only if Celery retry behavior is explicitly configured by the implementation plan.

The first version should not implement automatic retries by default. Re-running LLM-heavy tasks can be expensive and may duplicate external provider calls. Operators can resubmit a new run explicitly.

## Configuration

Environment variables:

- `DATABASE_URL`: PostgreSQL connection string.
- `REDIS_URL`: Redis connection string for Celery broker and result backend.
- `TRADINGAGENTS_API_TASK_TIME_LIMIT_SECONDS`: Celery hard time limit; default `3600`.
- `TRADINGAGENTS_API_WORKER_CONCURRENCY`: documented deployment knob; default recommended value `1`.

Existing TradingAgents environment variables remain server-controlled:

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

Provider API keys also remain server-controlled. Clients cannot supply provider keys in request payloads.

## Deployment Commands

API process:

```bash
uvicorn tradingagents.api.app:app --host 0.0.0.0 --port 8000
```

Worker process:

```bash
celery -A tradingagents.worker.celery_app worker --loglevel=info --concurrency=1
```

Required services:

- PostgreSQL reachable by `DATABASE_URL`.
- Redis reachable by `REDIS_URL`.

## Package Dependencies

The implementation will need to add dependencies:

- `fastapi`
- `uvicorn`
- `celery`
- `sqlalchemy`
- `psycopg[binary]` or `psycopg2-binary`
- `sse-starlette` or native `StreamingResponse`

Use the smallest dependency set that keeps the implementation clear. If native FastAPI `StreamingResponse` is sufficient for SSE, avoid adding `sse-starlette`.

The implementation should also include `tradingagents.api*` and `tradingagents.worker*` in package discovery if setuptools does not already include them.

## Error Handling

Request validation errors return FastAPI's normal `422` response.

Domain validation errors return `400`, for example:

- crypto request includes `fundamentals`.
- unsupported analyst key.
- future trade date.
- invalid ticker characters.

Unknown run returns `404`.

Result requested before completion returns `409`.

Failed run result request returns `409` with the stored failure message.

Worker exceptions are persisted to PostgreSQL before the task exits.

## Testing Strategy

The implementation should be test-first.

Minimum test coverage:

- Request validation accepts valid analysis requests.
- Request validation rejects invalid ticker.
- Request validation rejects future date.
- Request validation rejects crypto fundamentals.
- `POST /runs` inserts run and queued event, then enqueues Celery task.
- `GET /runs/{run_id}` returns persisted run metadata.
- `GET /runs/{run_id}/result` returns `409` before completion.
- `GET /runs/{run_id}/result` returns stored result after completion.
- Worker success path writes result and `run_succeeded`.
- Worker failure path writes failure state and `run_failed`.
- SSE endpoint emits historical events in order.

Tests should not call real LLMs or market data providers. Worker tests should patch `TradingAgentsGraph` or inject a fake analysis executor.

## Security and Operations Notes

Because first-version application-level auth is disabled, production deployment must put the service behind one of:

- private network only;
- firewall allowlist;
- reverse proxy with auth;
- API gateway;
- VPN.

Do not expose the raw service port directly to the public internet.

Run Celery worker concurrency conservatively. Each analysis can trigger many external LLM and market-data calls. The recommended first deployment is one API process and one worker process with `--concurrency=1`.

## Open Follow-Ups After First Version

- Add API key authentication.
- Add cancellation endpoint.
- Add idempotency key support for `POST /runs`.
- Add fine-grained LangGraph progress events by streaming worker chunks.
- Add retention policy for old runs/results/events.
- Add admin endpoint for failed run inspection.
- Add Docker Compose profile with API, worker, PostgreSQL, and Redis.

