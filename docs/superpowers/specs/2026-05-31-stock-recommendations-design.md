# Stock Recommendations Design

Date: 2026-05-31  
Branch: `phase/9-broker-integration`  
Status: design approved for planning

## Goal

Replace the sidebar's full-page "Refresh Data" action with a stock recommendation workflow:

- Store each user's watchlist in the application database, not in environment variables.
- Use the user's existing analysis model settings to recommend 5 stocks.
- Save recommendation batches as history.
- Let the user manually select recommended stocks before analysis starts.
- Create normal analysis runs for selected recommendations and link them back to the recommendation items.

This is a recommendation and triage feature, not an auto-trading feature. It should not place orders or create trade approvals directly.

## Confirmed Decisions

- Recommendation scope: user watchlist first, with model-expanded recommendations allowed.
- Analysis trigger: manual only. Recommendations go into a confirmation list first.
- Watchlist source: persisted per-user settings in the database.
- Recommendation history: keep every batch so users can review what was recommended and what was later analyzed.
- Layout: standalone Recommendations workspace, reachable from the sidebar.
- Batch size: fixed at 5 recommendations for the first version.
- Recommendation input mode: lightweight. Use watchlist, recent analysis history, date, and prompt/schema. Do not scan live market data.
- Model source: use the user's analysis model configuration. Prefer the quick model for recommendation generation.
- Analysis parameters from recommendation: default values only: `asset_type=stock`, today's date, all analysts enabled.

## Product Flow

1. User opens `/recommendations` from the sidebar.
2. User edits and saves a persistent watchlist.
3. User clicks "Generate Recommendations".
4. Backend loads the user's model settings, watchlist, and recent analysis history.
5. Backend asks the configured analysis model's quick LLM for exactly 5 recommendations.
6. Backend validates ticker syntax, saves a recommendation batch and item rows, and returns the batch.
7. User reviews reasons, risks, source, and priority for each recommended ticker.
8. User manually checks one or more items and clicks "Start Analysis".
9. Backend creates one normal analysis run per selected item using default analysis parameters.
10. Each recommendation item records its linked `run_id` and moves to `analysis_queued`.
11. Historical batches remain visible and link to created analysis runs.

## Sidebar Change

Current `Sidebar` has a "Refresh Data" button that calls `location.reload()`. Replace it with a navigation action:

- Label: "Recommend Stocks" / "推荐股票"
- Destination: `/recommendations`
- No full-page reload.

The "Last refresh" timestamp should be removed or renamed to avoid implying a global page refresh. If retained, it should refer only to the latest recommendation batch timestamp.

## Frontend Design

Add route:

```text
/recommendations
```

Add sidebar item under the Analysis group:

```text
Recommendations
Agent Reasoning
New Analysis
```

Recommendations page sections:

1. Watchlist Settings
   - Editable ticker input area.
   - Save button.
   - Show validation errors for invalid ticker symbols.
   - Persist to backend immediately on save.

2. Generate Recommendations
   - Primary button: "Generate Recommendations".
   - Disabled while generation is pending.
   - If model settings are missing, show a link to `/settings/model`.

3. Current Batch
   - Table or dense cards for the latest batch.
   - Fields: checkbox, ticker, source, priority, reason, risk, status, linked run.
   - User can select recommended items whose status is still `recommended`.
   - Button: "Start Analysis for Selected".

4. History
   - List previous batches by creation time.
   - Expanding a batch shows item details and linked run status.
   - Historical data is read-only except links to analysis details.

The page should use existing quiet dashboard styling: dense rows, restrained cards, no marketing hero.

## Backend API

Add router prefix:

```text
/recommendations
```

Endpoints:

```http
GET /recommendations/watchlist
PUT /recommendations/watchlist
POST /recommendations/generate
GET /recommendations/batches
GET /recommendations/batches/{batch_id}
POST /recommendations/batches/{batch_id}/analyze
```

### GET /recommendations/watchlist

Returns the current user's watchlist. If none exists, return an empty list.

Response:

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA"],
  "updated_at": "2026-05-31T10:00:00Z"
}
```

### PUT /recommendations/watchlist

Request:

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]
}
```

Validation:

- Normalize to uppercase.
- Use the same ticker pattern as analysis runs.
- Remove duplicates while preserving order.
- Require at least 1 ticker.
- Cap at 50 tickers for the first version.

### POST /recommendations/generate

Generates and saves one new batch for the current user.

Request body can be empty in v1:

```json
{}
```

Response:

```json
{
  "batch_id": "rec_...",
  "status": "succeeded",
  "created_at": "2026-05-31T10:05:00Z",
  "items": [
    {
      "item_id": "reci_...",
      "ticker": "NVDA",
      "source": "watchlist",
      "priority": 1,
      "reason": "Strong AI infrastructure momentum...",
      "risk": "High valuation and earnings sensitivity...",
      "status": "recommended",
      "run_id": null
    }
  ]
}
```

Failure cases:

- `409`: model settings not configured.
- `409`: watchlist not configured.
- `502`: model call failed or returned unusable output.

### POST /recommendations/batches/{batch_id}/analyze

Creates analysis runs for selected recommendation items.

Request:

```json
{
  "item_ids": ["reci_1", "reci_2"]
}
```

Behavior:

- Only current user's batch items are allowed.
- Only `recommended` items can create runs.
- Each created run uses:
  - `asset_type = "stock"`
  - `trade_date = date.today()`
  - `analysts = ["market", "social", "news", "fundamentals"]`
  - the user's saved model settings snapshot, exactly like `POST /runs`
- The same capacity checks as `POST /runs` should apply.
- Partial success is allowed: successful items keep their run links; failed items remain `recommended` and include an error in the response.

Response:

```json
{
  "created": [
    {"item_id": "reci_1", "ticker": "NVDA", "run_id": "run_..."}
  ],
  "failed": [
    {"item_id": "reci_2", "ticker": "MSFT", "detail": "too many queued analysis runs"}
  ]
}
```

## Data Model

Additive tables:

### `user_watchlists`

- `user_id` primary key, foreign key to `users.user_id`
- `tickers` JSON list
- `created_at`
- `updated_at`

### `recommendation_batches`

- `batch_id` primary key
- `user_id` indexed
- `status`: `succeeded` or `failed`
- `watchlist_snapshot` JSON list
- `model_snapshot` JSON object with provider/model/backend metadata, but no decrypted API key
- `prompt_version`
- `error`
- `created_at`

### `recommendation_items`

- `item_id` primary key
- `batch_id` foreign key
- `user_id` indexed
- `ticker` indexed
- `source`: `watchlist` or `model_expansion`
- `priority` integer, 1 is highest
- `reason` text
- `risk` text
- `status`: `recommended`, `analysis_queued`, `analysis_failed`, `ignored`
- `run_id` nullable foreign key to `analysis_runs.run_id`
- `error` nullable text
- `created_at`
- `updated_at`

Keep `user_id` on item rows as a denormalized authorization guard, matching the repository style used elsewhere.

## Recommendation Generation

Create a small service, for example `tradingagents/api/recommendation_service.py`.

Inputs:

- Current user id
- User watchlist
- Recent analysis summaries for the same user
- Current date
- User model settings snapshot

The service constructs a focused prompt:

- Recommend exactly 5 stock tickers.
- Prefer the watchlist, but allow model-expanded ideas when justified.
- Return structured JSON with ticker, source, priority, reason, and risk.
- Do not invent analysis results.
- Reasons and risks should be concise and suitable for pre-analysis triage.

Use the existing LLM client factory with:

- `llm_provider` from user model settings
- `quick_think_llm` as the model
- `backend_url` from settings
- decrypted user API key when present, otherwise service env fallback via the existing LLM client path

Output validation:

- Parse structured output with Pydantic when possible.
- Reject invalid ticker syntax.
- Deduplicate tickers.
- If fewer than 5 valid items remain, save only valid items and mark the batch `succeeded` if at least 1 item exists.
- If no valid items remain, fail the request with `502` and do not create a misleading empty current batch.

## Recent Analysis Context

Use recent completed analysis runs for the same user as lightweight context:

- Limit to the last 10 succeeded runs.
- Include ticker, trade date, final decision, and a short final decision excerpt.
- Do not include full reports; recommendation should remain cheap.

This gives the model continuity without running market data tools.

## Authorization

- All recommendation endpoints require login.
- `viewer` can view recommendation history and watchlist.
- `operator` and `admin` can generate recommendations and create analysis runs.
- If product wants viewers to generate recommendations later, that can be relaxed independently from analysis creation.

## Error Handling

- Missing model settings: show a clear call to action linking to model settings.
- Missing watchlist: prompt the user to save a watchlist first.
- Invalid watchlist tickers: return field-level validation errors.
- Model timeout/provider failure: do not create an empty batch; show a retryable error.
- Partial analysis creation failure: show per-item failures and keep failed items selectable.
- Duplicate selected item already linked to a run: return it as failed with `already analyzed`.

## Tests

Backend:

- Watchlist get/put normalization, duplicate removal, validation, auth.
- Recommendation generation requires model settings and watchlist.
- Recommendation service parses valid structured output and rejects invalid tickers.
- Batch/item persistence and current/history retrieval are user-scoped.
- Analyze endpoint creates runs with default parameters.
- Analyze endpoint handles capacity failures and partial success.
- Non-owner cannot access another user's batch.

Frontend:

- Settings form saves and reloads watchlist.
- Generate button calls API and renders batch items.
- Missing model settings links to `/settings/model`.
- Selecting items and starting analysis shows created run links.
- History renders previous batches.
- Sidebar no longer calls `location.reload()`.

## Out Of Scope

- Automatic analysis of recommendations.
- Real-time market/news scanning for recommendation input.
- Per-recommendation date or analyst customization.
- Dedicated recommendation model settings.
- Trading proposals or order placement from recommendations.
- Recommendation performance scoring beyond saved history.
