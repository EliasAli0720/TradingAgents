# User Model Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user model settings APIs and make analysis runs use a database-backed model config snapshot instead of built-in LLM defaults.

**Architecture:** Store each user's current LLM settings in `user_model_settings`. When `POST /runs` is called, copy that user's settings into `analysis_runs.llm_config`; the worker executes with that immutable snapshot. Existing auth, CSRF, role checks, SQLAlchemy repositories, and FastAPI routers are reused.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, existing cookie session + CSRF auth.

---

## File Structure

- Modify `tradingagents/api/models.py`: add `UserModelSetting` and `AnalysisRun.llm_config`.
- Modify `tradingagents/api/schemas.py`: add model settings request/response schemas.
- Create `tradingagents/api/model_settings_repository.py`: persistence for per-user model settings.
- Create `tradingagents/api/routers/settings.py`: `GET/PUT /settings/model`.
- Modify `tradingagents/api/app.py`: include settings router.
- Modify `tradingagents/api/repositories.py`: accept and store run `llm_config`.
- Modify `tradingagents/api/routers/runs.py`: require user model settings before enqueue.
- Modify `tradingagents/worker/analysis.py`: accept `llm_config` and override only LLM fields.
- Modify `tradingagents/worker/jobs.py`: pass `run.llm_config` into the executor and fail old runs without snapshots.
- Add tests:
  - `tests/api/test_model_settings.py`
  - update `tests/api/test_runs_routes.py`
  - update `tests/worker/test_jobs.py`

## Task 1: Model Settings Persistence

- [ ] Write failing tests for `UserModelSetting` and repository upsert/read.
- [ ] Add SQLAlchemy model and repository.
- [ ] Run targeted tests until green.
- [ ] Commit `feat(api): add user model settings persistence`.

## Task 2: Settings Routes

- [ ] Write failing route tests for unauthenticated access, missing settings, successful PUT/GET, invalid provider, and invalid backend URL.
- [ ] Add Pydantic schemas and `tradingagents/api/routers/settings.py`.
- [ ] Include router in app.
- [ ] Run targeted route tests until green.
- [ ] Commit `feat(api): add model settings routes`.

## Task 3: Run Snapshot

- [ ] Write failing route tests proving `POST /runs` returns `409` when the current user has no model settings.
- [ ] Write failing route test proving configured users create runs with `analysis_runs.llm_config`.
- [ ] Add `AnalysisRun.llm_config`, repository parameter, and route lookup.
- [ ] Run targeted route/repository tests until green.
- [ ] Commit `feat(api): snapshot model settings on runs`.

## Task 4: Worker Uses Snapshot

- [ ] Write failing worker tests proving executor receives `llm_config` and old runs without `llm_config` fail.
- [ ] Change worker executor signature and `run_tradingagents_analysis()` to use run snapshot.
- [ ] Run worker tests until green.
- [ ] Commit `feat(worker): use run model config snapshot`.

## Task 5: Verification

- [ ] Run `uv run pytest tests/api tests/worker -q`.
- [ ] Run `uv run pytest tests -q`.
- [ ] Run `uv run python -m compileall -q tradingagents tradingbot cli tests`.
- [ ] Smoke import API and worker.
- [ ] Commit any final documentation updates.
