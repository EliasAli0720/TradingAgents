# Model API Key Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure model API key management with user-specific encrypted keys, service-level fallback keys, validation, masked responses, and key clearing.

**Architecture:** Store user keys encrypted in `user_model_settings`, never return plaintext, and snapshot the decrypted key only into queued run configuration. Worker passes a snapshot key to LLM clients so user keys take priority, while existing provider environment variables remain the service fallback.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, cryptography Fernet.

---

### Task 1: API Key Crypto Boundary

**Files:**
- Create: `tradingagents/api/crypto.py`
- Modify: `tradingagents/api/config.py`
- Test: `tests/api/test_model_api_key_crypto.py`

- [ ] Write tests proving keys encrypt/decrypt, ciphertext does not contain plaintext, and missing encryption key fails clearly.
- [ ] Implement Fernet-based encryption using `MODEL_API_KEY_ENCRYPTION_KEY`.
- [ ] Add `model_api_key_encryption_key` to `ApiSettings`.
- [ ] Run `pytest tests/api/test_model_api_key_crypto.py -q`.

### Task 2: Persist And Mask User Keys

**Files:**
- Modify: `tradingagents/api/models.py`
- Modify: `tradingagents/api/model_settings_repository.py`
- Test: `tests/api/test_model_settings_repository.py`

- [ ] Write tests for saving, replacing, clearing, masking, and snapshotting decrypted user API keys.
- [ ] Add encrypted API key column to `UserModelSetting`.
- [ ] Extend repository methods to encrypt on write, decrypt for snapshots, return only masked metadata for reads, and clear the key.
- [ ] Run `pytest tests/api/test_model_settings_repository.py -q`.

### Task 3: Route Behavior

**Files:**
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/routers/settings.py`
- Test: `tests/api/test_model_settings_routes.py`

- [ ] Write tests for `PUT /settings/model` with optional `api_key`, masked `GET`, `DELETE /settings/model/api-key`, and `POST /settings/model/validate`.
- [ ] Extend request and response schemas.
- [ ] Implement key clear and validation endpoints.
- [ ] Run `pytest tests/api/test_model_settings_routes.py -q`.

### Task 4: Worker Key Priority

**Files:**
- Modify: `tradingagents/worker/analysis.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/worker/test_jobs.py`

- [ ] Write tests proving queued run snapshots include user keys and worker passes them to LLM client kwargs.
- [ ] Include decrypted user API key in run snapshot.
- [ ] Pass snapshot API key into `TradingAgentsGraph` provider kwargs so it overrides env fallback.
- [ ] Run `pytest tests/worker/test_jobs.py -q`.

### Task 5: Docs And Verification

**Files:**
- Modify: `.env.example`
- Modify: `RUNNING.md`
- Modify: `docs/api-endpoints-current.md`
- Modify: `pyproject.toml`

- [ ] Document `MODEL_API_KEY_ENCRYPTION_KEY`, user API key behavior, fallback behavior, and new endpoints.
- [ ] Ensure `cryptography` is a declared dependency.
- [ ] Run focused API and worker tests.
