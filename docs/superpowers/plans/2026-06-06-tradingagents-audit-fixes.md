# TradingAgents Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Ruflo audit findings from 2026-06-06 across desktop security, API auth/cookies, broker input validation, model endpoint safety, dataflow reliability, and project hygiene.

**Architecture:** Keep fixes narrow and test-first. Security-sensitive behavior moves into small testable helpers (`web/electron/app-protocol.cjs`, `tradingagents/api/url_validation.py`) instead of expanding route or Electron main-process files. Operational cleanup stays in config, lockfiles, and ignore rules so runtime behavior remains predictable.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, pytest, Electron main process, Node built-in test runner, Vite/React/TypeScript, pnpm, uv, Ruflo state files.

---

## File Structure

- Create `web/electron/app-protocol.cjs`: path-safe `app://` protocol helper and MIME map.
- Create `web/electron/app-protocol.test.cjs`: Node tests for SPA fallback and traversal rejection.
- Modify `web/electron/main.cjs`: delegate protocol registration to `app-protocol.cjs`.
- Modify `tradingagents/api/config.py`: add environment-aware cookie secure default and private backend URL setting.
- Modify `tradingagents/api/routers/auth.py`: preserve cookie deletion headers on logout.
- Modify `tests/api/test_config.py`: cover development cookie default and private backend URL setting.
- Modify `tests/api/test_auth_routes.py`: cover browser cookie deletion on logout.
- Create `web/src/api/csrf.ts`: configurable CSRF cookie-name reader.
- Modify `web/src/api/client.ts`: use `csrf.ts`.
- Modify `web/src/vite-env.d.ts` and `web/.env.example`: document `VITE_CSRF_COOKIE_NAME`.
- Create `tradingagents/api/url_validation.py`: backend URL allow/deny logic.
- Modify `tradingagents/api/routers/settings.py`: validate backend URLs before storing and probing.
- Modify `tradingagents/api/model_settings_repository.py`: clear stored API key when provider changes without a replacement.
- Modify `tradingagents/api/translation_settings_repository.py`: same provider-change key behavior for translation settings.
- Modify `tests/api/test_model_settings_routes.py`: cover backend URL rejection and provider-change key clearing.
- Modify `tests/api/test_model_settings_repository.py`: cover provider-change key clearing at repository level.
- Modify `tradingagents/api/routers/broker.py`: add positive/non-negative request constraints.
- Modify `tradingbot/broker/webull.py`: reject invalid order quantity/limit price before SDK calls.
- Modify `tests/api/test_broker_router.py`, `tests/api/test_broker_local.py`, `tests/test_webull_broker.py`: cover invalid quantities/prices.
- Modify `tradingagents/dataflows/alpha_vantage_common.py`: add request timeout.
- Modify `tradingagents/dataflows/yfinance_news.py`: enforce global-news lower date bound.
- Create `tests/test_alpha_vantage_common.py` and `tests/test_yfinance_news.py`: cover timeout and lookback filtering.
- Modify `.gitignore`: ignore Ruflo/agent runtime state.
- Remove tracked Ruflo/agent runtime files from git index: `.claude-flow/`, `.swarm/`.
- Modify `pyproject.toml` lock state via `uv lock`: align `uv.lock` with `httpx[socks]`.
- Modify `web/package.json`, `web/pnpm-workspace.yaml`, `web/pnpm-lock.yaml`: install lint dependencies, upgrade vulnerable frontend packages, remove ignored pnpm package-field config.
- Create `web/eslint.config.js`: flat ESLint config for TS/React.

---

## Task 0: Branch And Baseline

**Files:**
- Inspect only: all source files
- Modify later: none

- [ ] **Step 1: Start from a named branch**

Run:

```bash
git switch -c fix/ruflo-audit-findings
```

Expected: new branch `fix/ruflo-audit-findings`.

- [ ] **Step 2: Record current dirty state**

Run:

```bash
git status --short
```

Expected before cleanup: only Ruflo/agent runtime state is dirty, such as `.claude-flow/*`, `.swarm/*-wal`, `.swarm/*-shm`, and `ruvector.db`.

- [ ] **Step 3: Run the baseline verification**

Run:

```bash
python -m compileall -q tradingagents tradingbot cli
python -m pytest -q
uv pip check
uv lock --check
cd web && pnpm typecheck && pnpm build && pnpm audit --audit-level moderate
```

Expected:
- `compileall`: pass.
- `pytest`: current baseline is `655 passed, 1 skipped`.
- `uv pip check`: pass.
- `uv lock --check`: fail before Task 7 because lockfile needs update.
- `pnpm audit`: fail before Task 7 with the existing moderate advisories.

---

## Task 1: Secure Electron `app://` Protocol

**Files:**
- Create: `web/electron/app-protocol.cjs`
- Create: `web/electron/app-protocol.test.cjs`
- Modify: `web/electron/main.cjs`
- Modify: `web/package.json`

- [ ] **Step 1: Write failing protocol traversal tests**

Create `web/electron/app-protocol.test.cjs`:

```javascript
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { resolveAppFile } = require('./app-protocol.cjs');

function makeDist() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-app-protocol-'));
  const dist = path.join(root, 'dist');
  fs.mkdirSync(path.join(dist, 'assets'), { recursive: true });
  fs.writeFileSync(path.join(dist, 'index.html'), '<html></html>');
  fs.writeFileSync(path.join(dist, 'assets', 'index.js'), 'console.log("ok");');
  fs.writeFileSync(path.join(root, 'secret.json'), '{"secret":true}');
  return { root, dist };
}

test('resolveAppFile serves existing files under dist', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/assets/index.js');
  assert.equal(resolved.filePath, path.join(dist, 'assets', 'index.js'));
  assert.equal(resolved.contentType, 'text/javascript');
});

test('resolveAppFile falls back to index.html for SPA routes', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/analysis/run_123');
  assert.equal(resolved.filePath, path.join(dist, 'index.html'));
  assert.equal(resolved.contentType, 'text/html');
});

test('resolveAppFile rejects encoded traversal outside dist', () => {
  const { dist } = makeDist();
  const resolved = resolveAppFile(dist, 'app://local/%2e%2e/secret.json');
  assert.equal(resolved, null);
});
```

- [ ] **Step 2: Add a test script and run it red**

Modify `web/package.json` scripts:

```json
"electron:test": "node --test electron/*.test.cjs"
```

Run:

```bash
cd web && pnpm electron:test
```

Expected: fail because `web/electron/app-protocol.cjs` does not exist.

- [ ] **Step 3: Implement the safe protocol helper**

Create `web/electron/app-protocol.cjs`:

```javascript
'use strict';

const path = require('node:path');
const fs = require('node:fs');

const MIME = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json',
};

function isWithin(root, filePath) {
  const resolvedRoot = path.resolve(root);
  const resolvedFile = path.resolve(filePath);
  const rootWithSep = resolvedRoot.endsWith(path.sep) ? resolvedRoot : `${resolvedRoot}${path.sep}`;
  return resolvedFile === resolvedRoot || resolvedFile.startsWith(rootWithSep);
}

function resolveAppFile(distDir, requestUrl, existsSync = fs.existsSync) {
  const root = path.resolve(distDir);
  const { pathname } = new URL(requestUrl);
  const decoded = decodeURIComponent(pathname);
  const relativePath = decoded.replace(/^\/+/, '');
  const candidate = path.resolve(root, relativePath);

  if (!isWithin(root, candidate)) {
    return null;
  }

  let filePath = candidate;
  if (!path.extname(relativePath) || !existsSync(filePath)) {
    filePath = path.join(root, 'index.html');
  }

  if (!isWithin(root, filePath)) {
    return null;
  }

  return {
    filePath,
    contentType: MIME[path.extname(filePath)] || 'application/octet-stream',
  };
}

function registerAppProtocol(protocol, distDir) {
  protocol.handle('app', async (request) => {
    const resolved = resolveAppFile(distDir, request.url);
    if (resolved === null) {
      return new Response('Not found', { status: 404 });
    }
    try {
      const data = await fs.promises.readFile(resolved.filePath);
      return new Response(data, { headers: { 'content-type': resolved.contentType } });
    } catch {
      return new Response('Not found', { status: 404 });
    }
  });
}

module.exports = { MIME, resolveAppFile, registerAppProtocol };
```

- [ ] **Step 4: Wire Electron main to the helper**

Modify `web/electron/main.cjs`:

```javascript
const { app, BrowserWindow, protocol, shell, ipcMain } = require('electron');
const path = require('node:path');
const { Sidecar } = require('./sidecar.cjs');
const { registerAppProtocol } = require('./app-protocol.cjs');
```

Remove the local `fs` import, local `MIME` object, and local `registerAppProtocol()` function. Keep this call unchanged:

```javascript
if (!isDev) registerAppProtocol(protocol, DIST_DIR);
```

- [ ] **Step 5: Verify**

Run:

```bash
cd web && pnpm electron:test && pnpm typecheck && pnpm build
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add web/electron/main.cjs web/electron/app-protocol.cjs web/electron/app-protocol.test.cjs web/package.json web/pnpm-lock.yaml
git commit -m "fix(desktop): contain app protocol file access"
```

---

## Task 2: Fix API Cookie Defaults And Logout Cookie Clearing

**Files:**
- Modify: `tradingagents/api/config.py`
- Modify: `tradingagents/api/routers/auth.py`
- Modify: `.env.example`
- Modify: `tests/api/test_config.py`
- Modify: `tests/api/test_auth_routes.py`
- Modify: `docs/current-system/01-api-auth-data.md`

- [ ] **Step 1: Add failing config and logout tests**

Append to `tests/api/test_config.py`:

```python
def test_cookie_secure_defaults_false_for_development(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.delenv("TRADINGAGENTS_API_COOKIE_SECURE", raising=False)

    settings = get_api_settings()

    assert settings.cookie_secure is False


def test_cookie_secure_explicit_env_overrides_development(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_SECURE", "true")

    settings = get_api_settings()

    assert settings.cookie_secure is True
```

Append to `tests/api/test_auth_routes.py`:

```python
def test_logout_clears_browser_cookies():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    _login(c, "alice", "hunter22a")

    csrf = c.cookies.get("tradingagents_csrf")
    r = c.post("/auth/logout", headers={"X-CSRF-Token": csrf})

    assert r.status_code == 204
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert "tradingagents_session=" in set_cookie
    assert "tradingagents_csrf=" in set_cookie
    assert "max-age=0" in set_cookie
    assert c.cookies.get("tradingagents_session") is None
    assert c.cookies.get("tradingagents_csrf") is None
```

- [ ] **Step 2: Run tests red**

Run:

```bash
python -m pytest tests/api/test_config.py::test_cookie_secure_defaults_false_for_development tests/api/test_auth_routes.py::test_logout_clears_browser_cookies -q
```

Expected: both tests fail on current code.

- [ ] **Step 3: Implement environment-aware cookie default**

Modify `tradingagents/api/config.py`:

```python
def _default_cookie_secure() -> bool:
    env = os.environ.get("TRADINGAGENTS_API_ENV", "production").strip().lower()
    return env not in {"development", "dev", "local", "test"}
```

Change the `ApiSettings` construction:

```python
cookie_secure=_env_bool("TRADINGAGENTS_API_COOKIE_SECURE", _default_cookie_secure()),
```

- [ ] **Step 4: Preserve logout cookie deletion headers**

Modify `tradingagents/api/routers/auth.py` logout:

```python
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None
```

Do not return a new `Response` object from this endpoint.

- [ ] **Step 5: Document local cookie setting**

Add to `.env.example` under the analysis API environment block:

```dotenv
TRADINGAGENTS_API_COOKIE_SECURE=false
```

Update `docs/current-system/01-api-auth-data.md` so the local HTTP guidance states:

```markdown
For local HTTP development, set `TRADINGAGENTS_API_ENV=development` or `TRADINGAGENTS_API_COOKIE_SECURE=false`; production HTTPS should keep `TRADINGAGENTS_API_COOKIE_SECURE=true`.
```

- [ ] **Step 6: Verify**

Run:

```bash
python -m pytest tests/api/test_config.py tests/api/test_auth_routes.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/api/config.py tradingagents/api/routers/auth.py .env.example docs/current-system/01-api-auth-data.md tests/api/test_config.py tests/api/test_auth_routes.py
git commit -m "fix(api): align auth cookies with local and logout behavior"
```

---

## Task 3: Make Frontend CSRF Cookie Name Configurable

**Files:**
- Create: `web/src/api/csrf.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/vite-env.d.ts`
- Modify: `web/.env.example`

- [ ] **Step 1: Extract CSRF cookie handling**

Create `web/src/api/csrf.ts`:

```typescript
export const CSRF_COOKIE_NAME =
  import.meta.env.VITE_CSRF_COOKIE_NAME?.trim() || 'tradingagents_csrf';

export function readCookie(name: string): string | null {
  const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function readCsrfToken(): string | null {
  return readCookie(CSRF_COOKIE_NAME);
}
```

- [ ] **Step 2: Use the helper from the Axios client**

Modify `web/src/api/client.ts`:

```typescript
import axios, { AxiosError } from 'axios';
import { readCsrfToken } from './csrf';
```

Remove the local `readCookie` function. Change the interceptor:

```typescript
    const csrf = readCsrfToken();
    if (csrf) config.headers.set('X-CSRF-Token', csrf);
```

- [ ] **Step 3: Type and document the env variable**

Modify `web/src/vite-env.d.ts`:

```typescript
  readonly VITE_CSRF_COOKIE_NAME?: string;
```

Modify `web/.env.example`:

```dotenv
VITE_CSRF_COOKIE_NAME=tradingagents_csrf
```

- [ ] **Step 4: Verify**

Run:

```bash
cd web && pnpm typecheck && pnpm build
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/csrf.ts web/src/api/client.ts web/src/vite-env.d.ts web/.env.example
git commit -m "fix(web): make csrf cookie name configurable"
```

---

## Task 4: Harden Model Backend URLs And Provider Key Switching

**Files:**
- Create: `tradingagents/api/url_validation.py`
- Modify: `tradingagents/api/config.py`
- Modify: `tradingagents/api/routers/settings.py`
- Modify: `tradingagents/api/model_settings_repository.py`
- Modify: `tradingagents/api/translation_settings_repository.py`
- Modify: `tests/api/test_model_settings_routes.py`
- Modify: `tests/api/test_model_settings_repository.py`

- [ ] **Step 1: Add failing repository tests for provider changes**

Append to `tests/api/test_model_settings_repository.py`:

```python
def test_user_model_settings_repository_clears_api_key_when_provider_changes(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)

    repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
        api_key="sk-openai-abcdef123456",
    )

    repo.upsert(
        user_id="usr_1",
        llm_provider="anthropic",
        deep_think_llm="claude-opus-4-7",
        quick_think_llm="claude-haiku-4-5",
        backend_url=None,
    )

    assert repo.get("usr_1").encrypted_api_key is None
```

- [ ] **Step 2: Add failing route tests for private backend URLs**

Append to `tests/api/test_model_settings_routes.py`:

```python
def test_put_model_settings_rejects_private_backend_url_in_production(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", "false")
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "ollama",
            "deep_think_llm": "llama3.1",
            "quick_think_llm": "llama3.1",
            "backend_url": "http://127.0.0.1:11434/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert "private backend URLs are disabled" in response.json()["detail"]


def test_put_model_settings_allows_private_backend_url_when_enabled(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", "true")
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "ollama",
            "deep_think_llm": "llama3.1",
            "quick_think_llm": "llama3.1",
            "backend_url": "http://127.0.0.1:11434/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["backend_url"] == "http://127.0.0.1:11434/v1"
```

- [ ] **Step 3: Run tests red**

Run:

```bash
python -m pytest tests/api/test_model_settings_repository.py::test_user_model_settings_repository_clears_api_key_when_provider_changes tests/api/test_model_settings_routes.py::test_put_model_settings_rejects_private_backend_url_in_production -q
```

Expected: fail.

- [ ] **Step 4: Add URL validation helper**

Create `tradingagents/api/url_validation.py`:

```python
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeBackendUrl(ValueError):
    pass


def _is_private_address(raw: str) -> bool:
    address = ipaddress.ip_address(raw)
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_backend_url(url: str | None, *, allow_private: bool) -> str | None:
    if url is None:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeBackendUrl("backend_url must start with http:// or https://")
    if not parsed.hostname:
        raise UnsafeBackendUrl("backend_url must include a host")
    if allow_private:
        return url

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise UnsafeBackendUrl(f"backend_url host cannot be resolved: {host}") from exc

    for raw_address in addresses:
        if _is_private_address(raw_address):
            raise UnsafeBackendUrl(
                "private backend URLs are disabled; set "
                "TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS=true for trusted local deployments"
            )

    return url
```

- [ ] **Step 5: Add config flag**

Modify `tradingagents/api/config.py`:

```python
    allow_private_backend_urls: bool = False
```

In `get_api_settings()`:

```python
        allow_private_backend_urls=_env_bool(
            "TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS",
            os.environ.get("TRADINGAGENTS_API_ENV", "").strip().lower()
            in {"development", "dev", "local", "test"},
        ),
```

- [ ] **Step 6: Validate settings route input before storage**

Modify `tradingagents/api/routers/settings.py` imports:

```python
from tradingagents.api.config import get_api_settings
from tradingagents.api.url_validation import UnsafeBackendUrl, validate_backend_url
```

Add helper:

```python
def _safe_backend_url(value: str | None) -> str | None:
    try:
        return validate_backend_url(
            value,
            allow_private=get_api_settings().allow_private_backend_urls,
        )
    except UnsafeBackendUrl as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Use it in both model and translation `upsert` calls:

```python
        backend_url=_safe_backend_url(request.backend_url),
```

- [ ] **Step 7: Clear stored key on provider change without new key**

Modify `tradingagents/api/model_settings_repository.py` inside existing settings update:

```python
        provider_changed = settings.llm_provider != llm_provider
        settings.llm_provider = llm_provider
        settings.deep_think_llm = deep_think_llm
        settings.quick_think_llm = quick_think_llm
        settings.backend_url = backend_url
        if encrypted_api_key is not None:
            settings.encrypted_api_key = encrypted_api_key
        elif provider_changed:
            settings.encrypted_api_key = None
```

Apply the same pattern in `tradingagents/api/translation_settings_repository.py`:

```python
        provider_changed = settings.llm_provider != llm_provider
        settings.llm_provider = llm_provider
        settings.model = model
        settings.backend_url = backend_url
        if encrypted_api_key is not None:
            settings.encrypted_api_key = encrypted_api_key
        elif provider_changed:
            settings.encrypted_api_key = None
```

- [ ] **Step 8: Verify**

Run:

```bash
python -m pytest tests/api/test_model_settings_repository.py tests/api/test_model_settings_routes.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/api/url_validation.py tradingagents/api/config.py tradingagents/api/routers/settings.py tradingagents/api/model_settings_repository.py tradingagents/api/translation_settings_repository.py tests/api/test_model_settings_routes.py tests/api/test_model_settings_repository.py
git commit -m "fix(api): harden model endpoint and key switching"
```

---

## Task 5: Validate Broker Order Inputs Before External Calls

**Files:**
- Modify: `tradingagents/api/routers/broker.py`
- Modify: `tradingbot/broker/webull.py`
- Modify: `tests/api/test_broker_router.py`
- Modify: `tests/api/test_broker_local.py`
- Modify: `tests/test_webull_broker.py`

- [ ] **Step 1: Add failing API validation tests**

Append to `tests/api/test_broker_router.py`:

```python
def test_place_order_rejects_non_positive_qty():
    client, _app = _client()
    client.headers.update({"X-CSRF-Token": client.cookies.get("tradingagents_csrf")})

    response = client.post(
        "/broker/orders",
        json={"ticker": "AAPL", "qty": 0, "side": "buy", "order_type": "market"},
    )

    assert response.status_code == 422
```

Append to `tests/api/test_broker_local.py`:

```python
def test_manual_order_rejects_negative_quantity():
    client = _client()

    response = client.post(
        "/broker/orders/manual",
        json={
            "broker_order_id": "ord-bad",
            "account_id": "DU1",
            "ticker": "AAPL",
            "side": "buy",
            "order_type": "market",
            "quantity": -1,
        },
    )

    assert response.status_code == 422
```

Append to `tests/test_webull_broker.py`:

```python
def test_webull_rejects_non_positive_quantity_before_sdk_call():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="acct-1")

    with pytest.raises(ValueError, match="quantity must be greater than zero"):
        broker.submit_order("AAPL", 0, OrderSide.BUY, OrderType.MARKET)
```

- [ ] **Step 2: Run tests red**

Run:

```bash
python -m pytest tests/api/test_broker_router.py::test_place_order_rejects_non_positive_qty tests/api/test_broker_local.py::test_manual_order_rejects_negative_quantity tests/test_webull_broker.py::test_webull_rejects_non_positive_quantity_before_sdk_call -q
```

Expected: fail.

- [ ] **Step 3: Add Pydantic constraints to broker routes**

Modify `tradingagents/api/routers/broker.py` imports:

```python
from typing import Annotated, Any, Literal, Optional
```

Add aliases near schemas:

```python
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
```

Change request fields:

```python
class PreviewRequest(BaseModel):
    ticker: str
    qty: PositiveInt
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[PositiveFloat] = None
    time_in_force: str = "day"


class PlaceOrderRequest(BaseModel):
    ticker: str
    qty: PositiveInt
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[PositiveFloat] = None
    time_in_force: str = "day"
```

For local/manual inputs:

```python
class AccountSnap(BaseModel):
    cash: NonNegativeFloat
    portfolio_value: NonNegativeFloat
    buying_power: NonNegativeFloat
    equity: NonNegativeFloat


class LocalProposalRequest(BaseModel):
    run_id: str
    account: AccountSnap
    positions: list[PositionSnap] = []
    price: PositiveFloat


class ExecutedRequest(BaseModel):
    broker_order_id: str
    status: str = "submitted"
    filled_qty: NonNegativeFloat = 0.0
    filled_avg_price: Optional[PositiveFloat] = None
    limit_price: Optional[PositiveFloat] = None
    account_id: Optional[str] = None
    broker: str = "ibkr"


class ManualOrderRequest(BaseModel):
    broker_order_id: str
    account_id: str
    broker: str = "ibkr"
    ticker: str
    side: str
    order_type: str = "market"
    quantity: PositiveFloat
    status: str = "submitted"
    filled_qty: NonNegativeFloat = 0.0
    filled_avg_price: Optional[PositiveFloat] = None
    limit_price: Optional[PositiveFloat] = None
```

- [ ] **Step 4: Add Webull adapter guard**

Modify `tradingbot/broker/webull.py` `_order_payload()`:

```python
        if qty <= 0:
            raise ValueError("quantity must be greater than zero")
        if limit_price is not None and limit_price <= 0:
            raise ValueError("limit_price must be greater than zero")
```

Place these checks before `quantity = str(qty)`.

- [ ] **Step 5: Verify**

Run:

```bash
python -m pytest tests/api/test_broker_router.py tests/api/test_broker_local.py tests/test_webull_broker.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/routers/broker.py tradingbot/broker/webull.py tests/api/test_broker_router.py tests/api/test_broker_local.py tests/test_webull_broker.py
git commit -m "fix(broker): validate order inputs before placement"
```

---

## Task 6: Improve Dataflow Reliability And Lookback Correctness

**Files:**
- Modify: `tradingagents/dataflows/alpha_vantage_common.py`
- Modify: `tradingagents/dataflows/yfinance_news.py`
- Create: `tests/test_alpha_vantage_common.py`
- Create: `tests/test_yfinance_news.py`

- [ ] **Step 1: Add failing Alpha Vantage timeout test**

Create `tests/test_alpha_vantage_common.py`:

```python
import json

from tradingagents.dataflows import alpha_vantage_common as av


class _Response:
    text = "timestamp,close\n2026-01-01,1\n"

    def raise_for_status(self):
        return None


def test_make_api_request_sets_timeout(monkeypatch):
    captured = {}
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(av.requests, "get", fake_get)

    out = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert "timestamp,close" in out
    assert captured["timeout"] == 30.0
    assert captured["params"]["apikey"] == "demo"


def test_make_api_request_honours_timeout_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")
    monkeypatch.setenv("ALPHA_VANTAGE_TIMEOUT_SECONDS", "7.5")

    def fake_get(url, params, timeout):
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(av.requests, "get", fake_get)

    av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert captured["timeout"] == 7.5
```

- [ ] **Step 2: Add failing global news lookback test**

Create `tests/test_yfinance_news.py`:

```python
from tradingagents.dataflows import yfinance_news


class _Search:
    def __init__(self, query, news_count, enable_fuzzy_query):
        self.news = [
            {
                "content": {
                    "title": "old macro story",
                    "summary": "outside window",
                    "provider": {"displayName": "Wire"},
                    "canonicalUrl": {"url": "https://example.test/old"},
                    "pubDate": "2026-05-01T10:00:00Z",
                }
            },
            {
                "content": {
                    "title": "current macro story",
                    "summary": "inside window",
                    "provider": {"displayName": "Wire"},
                    "canonicalUrl": {"url": "https://example.test/current"},
                    "pubDate": "2026-06-05T10:00:00Z",
                }
            },
        ]


def test_global_news_filters_articles_before_lookback(monkeypatch):
    monkeypatch.setattr(yfinance_news.yf, "Search", _Search)
    monkeypatch.setattr(yfinance_news, "yf_retry", lambda fn: fn())

    out = yfinance_news.get_global_news_yfinance(
        curr_date="2026-06-06",
        look_back_days=7,
        limit=10,
    )

    assert "current macro story" in out
    assert "old macro story" not in out
```

- [ ] **Step 3: Run tests red**

Run:

```bash
python -m pytest tests/test_alpha_vantage_common.py tests/test_yfinance_news.py -q
```

Expected: fail.

- [ ] **Step 4: Add Alpha Vantage timeout**

Modify `tradingagents/dataflows/alpha_vantage_common.py`:

```python
def _request_timeout_seconds() -> float:
    return float(os.getenv("ALPHA_VANTAGE_TIMEOUT_SECONDS", "30"))
```

Change request call:

```python
    response = requests.get(
        API_BASE_URL,
        params=api_params,
        timeout=_request_timeout_seconds(),
    )
```

- [ ] **Step 5: Add lower-bound global news filter**

Modify `tradingagents/dataflows/yfinance_news.py` in the `if data.get("pub_date")` block:

```python
                    pub_naive = (
                        data["pub_date"].replace(tzinfo=None)
                        if hasattr(data["pub_date"], "replace")
                        else data["pub_date"]
                    )
                    if pub_naive < start_dt or pub_naive > curr_dt + relativedelta(days=1):
                        continue
```

- [ ] **Step 6: Verify**

Run:

```bash
python -m pytest tests/test_alpha_vantage_common.py tests/test_yfinance_news.py tests/test_dataflows_config.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/dataflows/alpha_vantage_common.py tradingagents/dataflows/yfinance_news.py tests/test_alpha_vantage_common.py tests/test_yfinance_news.py
git commit -m "fix(dataflows): bound external calls and news lookback"
```

---

## Task 7: Clean Project Hygiene, Lockfiles, And Frontend Tooling

**Files:**
- Modify: `.gitignore`
- Modify: `uv.lock`
- Modify: `web/package.json`
- Modify: `web/pnpm-lock.yaml`
- Modify: `web/pnpm-workspace.yaml`
- Create: `web/eslint.config.js`
- Remove from git index: `.claude-flow/`, `.swarm/`

- [ ] **Step 1: Ignore Ruflo and agent runtime state**

Add to `.gitignore`:

```gitignore
# Agent / Ruflo runtime state
.claude-flow/
.swarm/
ruvector.db
ruvector.db-*
```

- [ ] **Step 2: Remove tracked runtime state from git index while keeping local files**

Run:

```bash
git rm --cached -r .claude-flow .swarm
```

Expected: files are staged for removal from git, but local directories remain on disk.

- [ ] **Step 3: Update Python lockfile**

Run:

```bash
uv lock
uv lock --check
uv pip check
```

Expected:
- `uv.lock` records `httpx[socks]` and `socksio`.
- `uv lock --check`: pass.
- `uv pip check`: pass.

- [ ] **Step 4: Upgrade vulnerable frontend packages on compatible lines**

Run:

```bash
cd web
pnpm add vite@^6.4.3 @vitejs/plugin-react@^4.7.0 react-router-dom@^6.30.4
```

Expected: `package.json` and `pnpm-lock.yaml` update; app still uses React Router v6 APIs.

- [ ] **Step 5: Install ESLint tooling**

Run:

```bash
cd web
pnpm add -D eslint@^9.39.4 @eslint/js@^9.39.4 typescript-eslint@^8.60.1 eslint-plugin-react-hooks@^7.1.1 eslint-plugin-react-refresh@^0.5.2
```

- [ ] **Step 6: Add flat ESLint config**

Create `web/eslint.config.js`:

```javascript
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default [
  {
    ignores: ['dist/**', 'release/**', 'node_modules/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
];
```

- [ ] **Step 7: Remove ignored pnpm package-field config**

Remove this block from `web/package.json`:

```json
"pnpm": {
  "onlyBuiltDependencies": [
    "electron",
    "esbuild"
  ]
}
```

Modify `web/pnpm-workspace.yaml`:

```yaml
allowBuilds:
  electron: true
  electron-winstaller: true
  esbuild: true
```

- [ ] **Step 8: Verify frontend hygiene**

Run:

```bash
cd web
pnpm lint
pnpm typecheck
pnpm build
pnpm audit --audit-level moderate
```

Expected:
- `pnpm lint`: pass.
- `pnpm typecheck`: pass.
- `pnpm build`: pass.
- `pnpm audit --audit-level moderate`: pass or report only advisories unrelated to direct/transitive packages changed in this task. If audit still reports Vite, esbuild, or React Router, keep package constraints on patched versions and rerun `pnpm install`.
- pnpm no longer warns that `package.json` `pnpm.onlyBuiltDependencies` is ignored.

- [ ] **Step 9: Verify ignored runtime files**

Run:

```bash
git status --short
git status --ignored --short .claude-flow .swarm ruvector.db
```

Expected:
- `.claude-flow/` and `.swarm/` removals are staged.
- Local runtime files appear ignored, not untracked.

- [ ] **Step 10: Commit**

```bash
git add .gitignore uv.lock web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/eslint.config.js
git add -u .claude-flow .swarm
git commit -m "chore: clean agent state and frontend tooling"
```

---

## Task 8: Full Regression And Release Notes

**Files:**
- Modify: `RUNNING.md`
- Modify: `docs/current-system/01-api-auth-data.md`

- [ ] **Step 1: Document deployment knobs**

Add to `RUNNING.md`:

```markdown
## Security-sensitive deployment settings

- Local HTTP development should use `TRADINGAGENTS_API_ENV=development` or `TRADINGAGENTS_API_COOKIE_SECURE=false`.
- Production HTTPS should keep `TRADINGAGENTS_API_COOKIE_SECURE=true`.
- Production multi-tenant deployments should keep `TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS=false`.
- Trusted local LLM deployments such as Ollama may set `TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS=true`.
- If `TRADINGAGENTS_API_CSRF_COOKIE_NAME` changes, set `VITE_CSRF_COOKIE_NAME` to the same value when building the web frontend.
```

- [ ] **Step 2: Run full backend verification**

Run:

```bash
python -m compileall -q tradingagents tradingbot cli
python -m pytest -q
uv lock --check
uv pip check
```

Expected:
- compileall passes.
- pytest passes with one live-provider skip unless real `DEEPSEEK_API_KEY` is configured.
- `uv lock --check` passes.
- `uv pip check` passes.

- [ ] **Step 3: Run full frontend verification**

Run:

```bash
cd web
pnpm electron:test
pnpm lint
pnpm typecheck
pnpm build
pnpm audit --audit-level moderate
```

Expected: all pass.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat HEAD
git status --short
```

Expected:
- only intended changes remain.
- no `.swarm/*-wal`, `.swarm/*-shm`, `.claude-flow/neural/`, or `ruvector.db` untracked entries appear.

- [ ] **Step 5: Commit docs**

```bash
git add RUNNING.md docs/current-system/01-api-auth-data.md
git commit -m "docs: document secure local and production settings"
```

---

## Execution Order

1. Task 0 establishes the branch and baseline.
2. Task 1 should be first because it fixes the highest-risk local file access issue.
3. Tasks 2 and 3 can run independently after Task 1.
4. Task 4 should run before any production deployment.
5. Task 5 can run independently of Task 4.
6. Task 6 can run independently of Tasks 2-5.
7. Task 7 should run after source changes so dependency and ignore changes can be verified once.
8. Task 8 closes the branch with full regression and docs.

## Final Acceptance Criteria

- Electron `app://` requests cannot resolve outside `web/dist`.
- Local HTTP API login works without manually editing cookie settings when `TRADINGAGENTS_API_ENV=development`.
- Logout returns cookie deletion headers and TestClient/browser cookies are cleared.
- Frontend CSRF cookie name can be aligned with backend config.
- Production model backend URLs reject loopback/private/link-local/reserved addresses unless explicitly allowed.
- Switching model or translation provider without a new key clears the old encrypted key.
- Broker order endpoints and Webull adapter reject non-positive quantities and invalid limit prices before external calls.
- Alpha Vantage calls have a finite timeout.
- Yahoo global news output respects both lower and upper date bounds when article publish dates are available.
- Ruflo/agent runtime state is not tracked by git and generated runtime files are ignored.
- `uv lock --check`, `uv pip check`, backend pytest, frontend lint/typecheck/build/audit, and Electron protocol tests pass.

## Self-Review

- Spec coverage: every finding from `tradingagents-audit/audit-2026-06-06-deep-detection` maps to at least one task above.
- Type consistency: Pydantic aliases use `Annotated[..., Field(...)]`, matching Pydantic v2 already used in the repo.
- Test consistency: new tests use existing pytest patterns for API/backend and Node built-in `node --test` for Electron helper logic.
- Scope control: no UI redesign, no broker behavior rewrite, no React Router major migration.
