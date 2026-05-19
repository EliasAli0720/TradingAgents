# React/FastAPI Worker Frontend Separation Design

## Context

The `phase/5-frontend-refactor` branch has two Python-fronted user interfaces:

- The Rich/questionary CLI in `cli/main.py`, which configures and runs TradingAgents analysis.
- The Streamlit dashboard in `tradingbot/dashboard/`, which displays portfolio state, performance, trade history, agent reasoning, risk status, and manual quick trades.

The target is a full frontend separation: React becomes the primary user interface, while Python remains responsible for TradingAgents analysis, broker integration, risk checks, scheduling, persistence, and report generation.

## Goals

- Build a full React web application that replaces both the CLI analysis UI and the Streamlit dashboard.
- Add a FastAPI backend that exposes the existing Python functionality through stable HTTP and realtime APIs.
- Run long LLM analysis and trading jobs through a worker/queue layer, not directly inside request handlers.
- Support server or LAN single-user deployment with access-token authentication.
- Allow manual trades and approval of automated trade proposals from the web UI, with second confirmation and audit logging.
- Keep API keys and broker secrets on the backend only. The frontend may show whether required `.env` variables are configured, but must not display or store secret values.

## Non-Goals

- Multi-user roles, teams, or per-user portfolio isolation.
- Removing the existing CLI or Streamlit code in the first implementation pass.
- Enabling unauthenticated access to trading operations.
- Replacing the existing TradingAgents, TradingBot, broker, risk, or portfolio domain logic.

## Architecture

Use a separated web architecture inside the same repository:

- `apps/web/`: Vite + React + TypeScript frontend.
- Python FastAPI package, for example `tradingagents/api/`: REST API, auth, realtime event streams, settings, and web-facing orchestration.
- Worker package, for example `tradingagents/worker/` or `tradingbot/worker/`: queue consumers that execute long-running analysis and trading jobs.
- Redis + RQ for the queue layer.
- SQLite remains the first persistence backend, extending the current TradingBot database.
- Docker Compose should eventually run `redis`, `api`, `worker`, and `web`.

FastAPI request handlers enqueue long-running work and return ids. Workers execute `TradingAgentsGraph`, `AutoTrader`, broker, risk, and portfolio operations. All task lifecycle changes are written as events so the frontend can recover state after refresh or reconnect.

## Frontend Stack

Use:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query for server state
- A small event reducer for run/event stream state
- Plotly-compatible charting or a React chart library chosen during implementation for portfolio/performance charts

The visual direction should be a professional trading/analysis workbench: dense, scan-friendly, and operational. It should preserve the useful panel structure of the current CLI while giving Streamlit dashboard workflows a first-class navigation model.

## Frontend Pages

Use a left-sidebar application shell with:

- `Workbench`
- `Runs`
- `Portfolio`
- `Performance`
- `Trades`
- `Risk`
- `Approvals`
- `Settings`

### Analysis Workbench

Replaces the CLI flow.

Capabilities:

- Configure ticker, analysis date, output language, analysts, research depth, LLM provider, quick/deep models, provider-specific thinking settings, checkpoint behavior, and asset type.
- Validate ticker/date and disable provider choices whose backend API keys are missing.
- Create analysis runs through the API.
- Display realtime state: agent progress, messages, tool calls, token/tool stats, current report section, and final report.

### Runs / Reports

Shows historical and current analysis runs.

Capabilities:

- Filter by ticker, date, status, provider, and signal.
- Open a run detail page with 12-agent reasoning sections, final signal, report sections, event timeline, and export actions.
- Load existing report/log files from the current TradingAgents result directories.

### Portfolio

Replaces Streamlit `portfolio_view`.

Capabilities:

- Account KPIs: equity, cash, invested value, buying power, unrealized P&L.
- Current positions table.
- Allocation chart.
- Optional manual trade launcher.

### Performance

Replaces Streamlit `performance_view`.

Capabilities:

- Total return, realized P&L, Sharpe, max drawdown, win rate, total trades, avg win/loss, profit factor.
- Equity curve.
- Drawdown chart.
- Daily P&L chart.

### Trade History

Replaces Streamlit `trades_view`.

Capabilities:

- Trades table with filtering by ticker and side.
- Closed positions table.
- Per-trade linked agent reasoning, using the existing full-state logs when present.

### Risk Monitor

Replaces Streamlit `risk_view`.

Capabilities:

- Circuit breaker status.
- Total exposure vs configured cap.
- Cash reserve status.
- Position concentration vs single-position cap.
- Risk limit display.

### Approvals

New web workflow for human-in-the-loop automated trading.

Capabilities:

- List pending, approved, rejected, executed, and failed proposals.
- Show ticker, signal, proposed side/quantity/value, risk verdict, model reasoning, and generated timestamp.
- Approve or reject proposals.
- Approval requires second confirmation, such as typing `APPROVE {TICKER}`.
- Every approval/rejection writes audit records.

### Settings

Capabilities:

- Display backend environment status: configured provider keys, broker type, paper/live mode, DB path, results path, watchlist, risk limits, scheduler times.
- Allow editing non-secret runtime config such as watchlist, risk limits, and scheduler times where supported.
- Never expose API key values. Missing keys should display the required `.env` variable name.

## Backend API

All protected endpoints require access-token authentication.

### Auth

- `POST /api/auth/login`: validate configured access token and issue a session.
- `GET /api/auth/me`: return current access status.

### Settings

- `GET /api/settings`: provider, broker, risk, scheduler, watchlist, and API key configuration status.
- `PATCH /api/settings/runtime`: update non-secret runtime configuration.

### Analysis Runs

- `POST /api/runs`: create and enqueue an analysis run.
- `GET /api/runs`: list runs.
- `GET /api/runs/{run_id}`: get run detail.
- `GET /api/runs/{run_id}/events`: stream run events using SSE.
- `POST /api/runs/{run_id}/cancel`: request cancellation.
- `GET /api/runs/{run_id}/report`: return complete report as Markdown/JSON.

### Reports / Logs

- `GET /api/reports`: list available persisted reports and full-state logs.
- `GET /api/reports/{report_id}`: return segmented 12-agent content.
- `GET /api/reports/{report_id}/export?format=md|html|pdf`: export report.

### Portfolio

- `GET /api/portfolio/account`
- `GET /api/portfolio/positions`
- `GET /api/portfolio/snapshots`
- `GET /api/portfolio/performance`

### Trades

- `GET /api/trades`
- `GET /api/trades/{trade_id}`
- `POST /api/trades/manual`: submit manual trade; requires second confirmation.
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

## Realtime Event Model

Use a single event envelope:

```json
{
  "event_id": "evt_...",
  "run_id": "run_...",
  "type": "agent_status | message | tool_call | report_section | stats | approval_required | completed | failed",
  "timestamp": "2026-05-19T12:00:00Z",
  "payload": {}
}
```

`GET /api/runs/{run_id}/events` should first replay persisted events, then stream new events. The frontend should reconnect with the last seen event id where possible.

## Worker And Queue

Use Redis + RQ for the first implementation.

Worker responsibilities:

- Execute queued TradingAgents analysis runs.
- Execute AutoTrader watchlist runs.
- Execute post-market portfolio snapshots.
- Create approval records instead of directly executing trades when human approval is required.
- Execute approved trade proposals as queued jobs.
- Write run events, status changes, errors, and audit records.

RQ is preferred over Celery for the first version because it is simpler and sufficient for this project’s initial task model. The API and DB schema should keep enough abstraction to replace the queue later if needed.

## Persistence

Extend the existing SQLite portfolio database.

Keep existing tables:

- `trades`
- `snapshots`
- `closed_positions`

Add:

- `analysis_runs`: id, ticker, analysis date, asset type, provider/model config, status, timestamps, error summary, result references.
- `run_events`: id, run id, event type, JSON payload, timestamp.
- `approvals`: id, linked run/job/trade proposal, ticker, signal, side, quantity, estimated price/value, status, created/approved/rejected/executed timestamps, reason.
- `audit_log`: id, action, actor/session id, target type/id, payload summary, timestamp, outcome.

Run statuses:

- `queued`
- `running`
- `waiting_approval`
- `completed`
- `failed`
- `cancel_requested`
- `cancelled`
- `stale`

## Cancellation

Queued jobs can be cancelled before execution.

Running jobs use cooperative cancellation:

- API sets `cancel_requested`.
- Worker checks cancellation at safe boundaries, especially between graph chunks/nodes.
- Current LLM/provider calls may not stop immediately.
- UI should say that cancellation has been requested and will take effect after the current step.

## Security

Deployment is single-user LAN/server.

Required controls:

- Access token configured in backend environment.
- All API routes except login/health protected.
- Trade execution and approval routes require second confirmation.
- Backend never returns secret values.
- Settings may show only configured/missing status for API keys.
- Broker mode should be highly visible in UI: mock, paper, or live.
- All trade, approval, scheduler, and settings mutations write audit records.

## Error Handling

- Provider/API key missing: reject run creation with a clear missing env var.
- LLM/data/broker/risk errors: write `failed` events with readable summary and raw error class/message.
- Worker crash: API startup or maintenance task should mark old running jobs as `stale` or `failed`.
- SSE disconnect: frontend reconnects and replays persisted events.
- Trade failures: write audit records and show failure in Approvals/Trades.

## Testing Strategy

### Backend

- FastAPI route tests for settings, runs, portfolio, trades, approvals, and auth.
- Worker tests for event writing, failed tasks, approval-required tasks, and cancellation.
- DB tests for new tables, event append/replay, approval lifecycle, and audit log writes.
- Security tests for missing/invalid token, failed second confirmation, and secret redaction.

### Frontend

- Vitest tests for API client, run event reducer, and state mapping.
- React Testing Library tests for Workbench form, run detail, Approvals, and Settings.
- Playwright smoke tests for login, creating a mock run, watching event updates, viewing a report, and approving a mock proposal.

### Integration

- Docker Compose smoke test for `redis`, `api`, `worker`, and `web`.
- End-to-end mock broker path without real LLM or Alpaca.
- Optional live-provider tests guarded by environment variables.

## Implementation Notes

- Keep existing CLI and Streamlit code during the initial migration.
- Factor reusable CLI display/status logic into backend-neutral helpers only where needed; do not force React to mirror terminal-only abstractions.
- Prefer typed backend response schemas so frontend contracts remain stable.
- Start with mock broker and fake analysis worker fixtures for fast local UI development.
- Add Docker Compose only after API, worker, and web have independently working dev commands.
