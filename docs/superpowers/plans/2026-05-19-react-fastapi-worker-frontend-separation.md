# React/FastAPI Worker 前端分离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 React Web 主前端、FastAPI 后端和 Redis/RQ worker，把当前 CLI 分析界面与 Streamlit dashboard 分离为可部署的 Web 应用。

**Architecture:** 同仓库新增 `apps/web/` React 前端、`tradingagents/api/` FastAPI 后端、`tradingagents/worker/` worker 层，并复用现有 `TradingAgentsGraph` 与 `tradingbot` 领域逻辑。长任务只通过队列执行，状态和事件持久化到 SQLite，前端通过 REST + SSE 读取。第一轮保留 CLI 与 Streamlit，不删除旧入口。

**Tech Stack:** FastAPI, Pydantic, Redis, RQ, SQLite, pytest, Vite, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Vitest, React Testing Library, Playwright.

---

## Scope Split

这个规格包含多个子系统。实施时按以下顺序推进，每个任务都应该独立提交：

1. 后端基础设施：依赖、配置、DB schema、仓储层。
2. API 基础：认证、settings、health。
3. 任务模型：run 创建、事件持久化、SSE 回放。
4. Worker：队列抽象、fake analysis worker、真实 TradingAgents worker adapter。
5. 交易安全：approvals、manual trades、audit log。
6. Portfolio/Reports/Risk API：替代 Streamlit 数据接口。
7. React 基础：Vite、Tailwind、shadcn、API client、auth shell。
8. React 业务页：Workbench/Runs、Portfolio/Performance/Trades/Risk/Approvals/Settings。
9. Docker Compose 和端到端 smoke。

## File Structure

### Backend

- Create `tradingagents/api/__init__.py`: API package marker.
- Create `tradingagents/api/app.py`: FastAPI app factory and router registration.
- Create `tradingagents/api/config.py`: API env config, token config, Redis URL, DB path.
- Create `tradingagents/api/deps.py`: shared dependencies such as auth and service factories.
- Create `tradingagents/api/schemas.py`: API request/response schemas.
- Create `tradingagents/api/db.py`: SQLite connection and schema migration entrypoint.
- Create `tradingagents/api/repositories.py`: analysis run, event, approval, audit repositories.
- Create `tradingagents/api/services/settings.py`: settings read/update service.
- Create `tradingagents/api/services/runs.py`: run lifecycle and event service.
- Create `tradingagents/api/services/trading.py`: approval/manual-trade orchestration service.
- Create `tradingagents/api/routers/auth.py`: login/me routes.
- Create `tradingagents/api/routers/settings.py`: settings routes.
- Create `tradingagents/api/routers/runs.py`: run CRUD and SSE routes.
- Create `tradingagents/api/routers/reports.py`: report/log routes.
- Create `tradingagents/api/routers/portfolio.py`: account/positions/snapshots/performance routes.
- Create `tradingagents/api/routers/trades.py`: trade routes.
- Create `tradingagents/api/routers/risk.py`: risk routes.
- Create `tradingagents/api/routers/approvals.py`: approval routes.
- Create `tradingagents/api/routers/bot.py`: bot/scheduler routes.
- Create `tradingagents/worker/__init__.py`: worker package marker.
- Create `tradingagents/worker/queue.py`: Redis/RQ queue creation and enqueue helpers.
- Create `tradingagents/worker/jobs.py`: job functions for analysis, watchlist, snapshots, approved trades.
- Create `tradingagents/worker/runner.py`: CLI entrypoint for worker process.
- Modify `pyproject.toml`: add FastAPI, uvicorn, sse-starlette or native StreamingResponse support, rq, redis dependency if missing, and frontend-independent test deps if project chooses to keep them in optional groups.
- Modify `docker-compose.yml`: add `redis`, `api`, `worker`, `web` services after local commands work.

### Frontend

- Create `apps/web/package.json`: frontend scripts and dependencies.
- Create `apps/web/vite.config.ts`: Vite config with API proxy.
- Create `apps/web/tsconfig.json`, `apps/web/tsconfig.node.json`: TypeScript config.
- Create `apps/web/tailwind.config.ts`, `apps/web/postcss.config.js`, `apps/web/src/index.css`: Tailwind setup.
- Create `apps/web/src/main.tsx`: React bootstrap.
- Create `apps/web/src/App.tsx`: route shell.
- Create `apps/web/src/lib/api/client.ts`: authenticated fetch wrapper.
- Create `apps/web/src/lib/api/types.ts`: frontend API types matching backend schemas.
- Create `apps/web/src/lib/runs/eventReducer.ts`: run event reducer.
- Create `apps/web/src/components/layout/AppShell.tsx`: sidebar layout.
- Create `apps/web/src/components/auth/LoginPage.tsx`: token login.
- Create `apps/web/src/pages/WorkbenchPage.tsx`: analysis form and run creation.
- Create `apps/web/src/pages/RunDetailPage.tsx`: realtime run view.
- Create `apps/web/src/pages/RunsPage.tsx`: run list.
- Create `apps/web/src/pages/PortfolioPage.tsx`: account and positions.
- Create `apps/web/src/pages/PerformancePage.tsx`: metrics and charts.
- Create `apps/web/src/pages/TradesPage.tsx`: trades and closed positions.
- Create `apps/web/src/pages/RiskPage.tsx`: risk monitor.
- Create `apps/web/src/pages/ApprovalsPage.tsx`: approval queue.
- Create `apps/web/src/pages/SettingsPage.tsx`: env/config status.

### Tests

- Create `tests/api/test_auth.py`
- Create `tests/api/test_settings.py`
- Create `tests/api/test_run_repositories.py`
- Create `tests/api/test_runs_routes.py`
- Create `tests/api/test_sse_events.py`
- Create `tests/api/test_approvals.py`
- Create `tests/api/test_trades_security.py`
- Create `tests/api/test_portfolio_routes.py`
- Create `tests/worker/test_jobs.py`
- Create `apps/web/src/lib/runs/eventReducer.test.ts`
- Create `apps/web/src/lib/api/client.test.ts`
- Create `apps/web/src/pages/WorkbenchPage.test.tsx`
- Create `apps/web/src/pages/ApprovalsPage.test.tsx`
- Create `apps/web/e2e/smoke.spec.ts`

---

### Task 1: 后端依赖与配置骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `tradingagents/api/__init__.py`
- Create: `tradingagents/api/config.py`
- Create: `tradingagents/api/app.py`
- Test: `tests/api/test_settings.py`

- [ ] **Step 1: 写失败测试，验证 API config 默认值和密钥脱敏**

Create `tests/api/test_settings.py`:

```python
from tradingagents.api.config import ApiConfig


def test_api_config_uses_safe_defaults(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_API_TOKEN", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_REDIS_URL", raising=False)

    config = ApiConfig.from_env()

    assert config.redis_url == "redis://localhost:6379/0"
    assert config.api_token is None
    assert config.auth_enabled is False


def test_api_config_redacts_secret_values(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_TOKEN", "secret-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-value")

    config = ApiConfig.from_env()
    status = config.provider_key_status(["OPENAI_API_KEY", "GOOGLE_API_KEY"])

    assert config.auth_enabled is True
    assert status == {
        "OPENAI_API_KEY": {"configured": True},
        "GOOGLE_API_KEY": {"configured": False},
    }
    assert "sk-real-value" not in str(status)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_settings.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.api'`.

- [ ] **Step 3: 添加后端依赖**

Modify `pyproject.toml` dependencies by adding:

```toml
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "rq>=2.0.0",
```

`redis>=6.2.0` already exists in the current project and does not need to be duplicated.

- [ ] **Step 4: 创建 API package 和配置实现**

Create `tradingagents/api/__init__.py`:

```python
"""FastAPI web API for TradingAgents."""
```

Create `tradingagents/api/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ApiConfig:
    api_token: str | None
    redis_url: str
    db_path: str
    results_dir: str
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "ApiConfig":
        home = Path.home() / ".tradingagents"
        origins = os.getenv(
            "TRADINGAGENTS_API_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        return cls(
            api_token=os.getenv("TRADINGAGENTS_API_TOKEN") or None,
            redis_url=os.getenv("TRADINGAGENTS_REDIS_URL", "redis://localhost:6379/0"),
            db_path=os.getenv("TRADINGBOT_DB_PATH", str(home / "tradingbot.db")),
            results_dir=os.getenv("TRADINGAGENTS_RESULTS_DIR", str(home / "logs")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_token)

    def provider_key_status(self, env_vars: Iterable[str]) -> dict[str, dict[str, bool]]:
        return {
            env_var: {"configured": bool(os.getenv(env_var))}
            for env_var in env_vars
        }
```

Create `tradingagents/api/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingagents.api.config import ApiConfig


def create_app(config: ApiConfig | None = None) -> FastAPI:
    config = config or ApiConfig.from_env()
    app = FastAPI(title="TradingAgents API")
    app.state.api_config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
uv run --with pytest pytest tests/api/test_settings.py -q
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml tradingagents/api tests/api/test_settings.py
git commit -m "feat(api): add FastAPI config foundation"
```

---

### Task 2: SQLite schema 与仓储层

**Files:**
- Create: `tradingagents/api/db.py`
- Create: `tradingagents/api/repositories.py`
- Test: `tests/api/test_run_repositories.py`

- [ ] **Step 1: 写失败测试，验证 schema、run、event、audit**

Create `tests/api/test_run_repositories.py`:

```python
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import AuditRepository, RunEventRepository, RunRepository


def test_run_repository_creates_run_and_events(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))
    events = RunEventRepository(str(db_path))

    run = runs.create_run(
        ticker="SPY",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )
    events.append(run["id"], "agent_status", {"agent": "Market Analyst", "status": "running"})
    runs.update_status(run["id"], "running")

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])

    assert loaded["ticker"] == "SPY"
    assert loaded["status"] == "running"
    assert replay[0]["type"] == "agent_status"
    assert replay[0]["payload"]["agent"] == "Market Analyst"


def test_audit_repository_records_mutations(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    audit = AuditRepository(str(db_path))

    entry = audit.record(
        action="manual_trade_requested",
        actor="session:test",
        target_type="trade",
        target_id="draft",
        payload={"ticker": "AAPL", "side": "buy"},
        outcome="accepted",
    )

    rows = audit.list_recent(limit=10)
    assert entry["id"] == rows[0]["id"]
    assert rows[0]["payload"]["ticker"] == "AAPL"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_run_repositories.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: 实现 schema 初始化**

Create `tradingagents/api/db.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path


API_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    ticker TEXT NOT NULL,
    signal TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    estimated_price REAL NOT NULL,
    estimated_value REAL NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT,
    decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_api_schema(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(API_SCHEMA)
```

- [ ] **Step 4: 实现仓储层**

Create `tradingagents/api/repositories.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from tradingagents.api.db import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row)


def _decode_json_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    decoded = dict(row)
    for field in fields:
        if field in decoded and decoded[field] is not None:
            decoded[field.removesuffix("_json")] = json.loads(decoded.pop(field))
    return decoded


class RunRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_run(self, ticker: str, analysis_date: str, asset_type: str, config: dict[str, Any]) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs
                    (id, ticker, analysis_date, asset_type, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ticker.upper(), analysis_date, asset_type, json.dumps(config), "queued", now, now),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _decode_json_fields(_row_to_dict(row), ("config_json", "result_json"))

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM analysis_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_decode_json_fields(_row_to_dict(row), ("config_json", "result_json")) for row in rows]

    def update_status(self, run_id: str, status: str, error: str | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        result_json = json.dumps(result) if result is not None else None
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE analysis_runs
                SET status = ?, error = COALESCE(?, error), result_json = COALESCE(?, result_json), updated_at = ?
                WHERE id = ?
                """,
                (status, error, result_json, now, run_id),
            )
        return self.get_run(run_id)


class RunEventRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = f"evt_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO run_events (id, run_id, type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, run_id, event_type, json.dumps(payload), now),
            )
        return {"event_id": event_id, "run_id": run_id, "type": event_type, "timestamp": now, "payload": payload}

    def list_for_run(self, run_id: str, after_event_id: str | None = None) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        events = [
            {
                "event_id": row["id"],
                "run_id": row["run_id"],
                "type": row["type"],
                "timestamp": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
        if after_event_id is None:
            return events
        ids = [event["event_id"] for event in events]
        if after_event_id not in ids:
            return events
        return events[ids.index(after_event_id) + 1:]


class AuditRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def record(self, action: str, actor: str, target_type: str, target_id: str, payload: dict[str, Any], outcome: str) -> dict[str, Any]:
        audit_id = f"aud_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                    (id, action, actor, target_type, target_id, payload_json, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, action, actor, target_type, target_id, json.dumps(payload), outcome, now),
            )
        return {
            "id": audit_id,
            "action": action,
            "actor": actor,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
            "outcome": outcome,
            "created_at": now,
        }

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_decode_json_fields(_row_to_dict(row), ("payload_json",)) for row in rows]
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
uv run --with pytest pytest tests/api/test_run_repositories.py -q
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add tradingagents/api/db.py tradingagents/api/repositories.py tests/api/test_run_repositories.py
git commit -m "feat(api): add run event persistence"
```

---

### Task 3: 认证、Settings 和 Health API

**Files:**
- Create: `tradingagents/api/deps.py`
- Create: `tradingagents/api/schemas.py`
- Create: `tradingagents/api/routers/auth.py`
- Create: `tradingagents/api/routers/settings.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_auth.py`
- Test: `tests/api/test_settings.py`

- [ ] **Step 1: 写失败测试，验证 token 保护和 settings 脱敏**

Create `tests/api/test_auth.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def make_client(tmp_path, token="test-token"):
    config = ApiConfig(
        api_token=token,
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(config))


def test_login_rejects_invalid_token(tmp_path):
    client = make_client(tmp_path)

    response = client.post("/api/auth/login", json={"token": "wrong"})

    assert response.status_code == 401


def test_login_accepts_valid_token_and_me_requires_bearer(tmp_path):
    client = make_client(tmp_path)

    login = client.post("/api/auth/login", json={"token": "test-token"})
    assert login.status_code == 200
    assert login.json()["access_token"] == "test-token"

    denied = client.get("/api/auth/me")
    assert denied.status_code == 401

    allowed = client.get("/api/auth/me", headers={"Authorization": "Bearer test-token"})
    assert allowed.status_code == 200
    assert allowed.json()["authenticated"] is True
```

Append to `tests/api/test_settings.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def test_settings_reports_key_status_without_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    client = TestClient(create_app(config))

    response = client.get("/api/settings", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider_keys"]["OPENAI_API_KEY"]["configured"] is True
    assert "sk-secret" not in str(body)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_auth.py tests/api/test_settings.py -q
```

Expected: FAIL because routers/deps/schemas are missing.

- [ ] **Step 3: 实现 schemas**

Create `tradingagents/api/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    token: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    authenticated: bool


class KeyStatus(BaseModel):
    configured: bool


class SettingsResponse(BaseModel):
    auth_enabled: bool
    broker: str
    paper_trading: bool
    db_path: str
    results_dir: str
    provider_keys: dict[str, KeyStatus]
    watchlist: list[str]
    risk_limits: dict[str, float]
    scheduler: dict[str, str]
```

- [ ] **Step 4: 实现 auth dependency**

Create `tradingagents/api/deps.py`:

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tradingagents.api.config import ApiConfig

bearer = HTTPBearer(auto_error=False)


def get_config(request: Request) -> ApiConfig:
    return request.app.state.api_config


def require_auth(
    config: ApiConfig = Depends(get_config),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if not config.auth_enabled:
        return "local"
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if credentials.credentials != config.api_token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return "session:token"
```

- [ ] **Step 5: 实现 auth 和 settings routers**

Create `tradingagents/api/routers/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.schemas import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, config: ApiConfig = Depends(get_config)) -> LoginResponse:
    if config.auth_enabled and payload.token != config.api_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return LoginResponse(access_token=payload.token)


@router.get("/me", response_model=MeResponse)
def me(_: str = Depends(require_auth)) -> MeResponse:
    return MeResponse(authenticated=True)
```

Create `tradingagents/api/routers/settings.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.schemas import SettingsResponse
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingbot.config import TRADINGBOT_CONFIG

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(
    _: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> SettingsResponse:
    env_vars = sorted(set(PROVIDER_API_KEY_ENV.values()) | {"ALPACA_API_KEY", "ALPACA_API_SECRET"})
    provider_keys = config.provider_key_status(env_vars)
    return SettingsResponse(
        auth_enabled=config.auth_enabled,
        broker=TRADINGBOT_CONFIG.get("broker", "mock"),
        paper_trading=bool(TRADINGBOT_CONFIG.get("paper_trading", True)),
        db_path=config.db_path,
        results_dir=config.results_dir,
        provider_keys=provider_keys,
        watchlist=[ticker for ticker in TRADINGBOT_CONFIG.get("watchlist", []) if ticker],
        risk_limits={
            "max_single_position_pct": float(TRADINGBOT_CONFIG.get("max_single_position_pct", 0.10)),
            "max_total_exposure_pct": float(TRADINGBOT_CONFIG.get("max_total_exposure_pct", 0.80)),
            "daily_loss_limit_pct": float(TRADINGBOT_CONFIG.get("daily_loss_limit_pct", -0.02)),
            "min_cash_reserve": float(TRADINGBOT_CONFIG.get("min_cash_reserve", 1000.0)),
        },
        scheduler={
            "timezone": str(TRADINGBOT_CONFIG.get("timezone", "America/New_York")),
            "pre_market_time": str(TRADINGBOT_CONFIG.get("pre_market_time", "08:00")),
            "order_submission_time": str(TRADINGBOT_CONFIG.get("order_submission_time", "09:35")),
            "post_market_time": str(TRADINGBOT_CONFIG.get("post_market_time", "16:30")),
        },
    )
```

- [ ] **Step 6: 注册 routers 和初始化 schema**

Modify `tradingagents/api/app.py` to:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingagents.api.config import ApiConfig
from tradingagents.api.db import init_api_schema
from tradingagents.api.routers import auth, settings


def create_app(config: ApiConfig | None = None) -> FastAPI:
    config = config or ApiConfig.from_env()
    init_api_schema(config.db_path)
    app = FastAPI(title="TradingAgents API")
    app.state.api_config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(settings.router)
    return app


app = create_app()
```

Create `tradingagents/api/routers/__init__.py`:

```python
"""FastAPI routers for TradingAgents web API."""
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```bash
uv run --with pytest pytest tests/api/test_auth.py tests/api/test_settings.py -q
```

Expected: PASS.

- [ ] **Step 8: 提交**

```bash
git add tradingagents/api tests/api/test_auth.py tests/api/test_settings.py
git commit -m "feat(api): add auth and settings routes"
```

---

### Task 4: Runs API、事件服务和 SSE 回放

**Files:**
- Create: `tradingagents/api/services/runs.py`
- Create: `tradingagents/api/routers/runs.py`
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_runs_routes.py`
- Test: `tests/api/test_sse_events.py`

- [ ] **Step 1: 写失败测试，验证 run 创建、列表和事件回放**

Create `tests/api/test_runs_routes.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def make_client(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(config))


def test_create_and_list_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = make_client(tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    response = client.post(
        "/api/runs",
        headers=headers,
        json={
            "ticker": "spy",
            "analysis_date": "2026-05-19",
            "asset_type": "stock",
            "analysts": ["market", "news"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_think_llm": "gpt-5.4-mini",
            "deep_think_llm": "gpt-5.4",
            "output_language": "English",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["ticker"] == "SPY"
    assert created["status"] == "queued"

    listed = client.get("/api/runs", headers=headers).json()
    assert listed["runs"][0]["id"] == created["id"]
```

Create `tests/api/test_sse_events.py`:

```python
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import RunEventRepository, RunRepository


def test_event_repository_replays_after_last_event(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run("SPY", "2026-05-19", "stock", {})

    first = events.append(run["id"], "message", {"text": "one"})
    second = events.append(run["id"], "message", {"text": "two"})

    replay = events.list_for_run(run["id"], after_event_id=first["event_id"])

    assert [event["event_id"] for event in replay] == [second["event_id"]]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_runs_routes.py tests/api/test_sse_events.py -q
```

Expected: route test FAIL because `/api/runs` does not exist. Repository replay test may pass if Task 2 implemented correctly.

- [ ] **Step 3: 扩展 schemas**

Append to `tradingagents/api/schemas.py`:

```python
from typing import Literal


class CreateRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    asset_type: Literal["stock", "crypto"] = "stock"
    analysts: list[Literal["market", "social", "news", "fundamentals"]]
    research_depth: int = Field(ge=1, le=5)
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    checkpoint_enabled: bool = False


class RunResponse(BaseModel):
    id: str
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    config: dict
    error: str | None = None
    result: dict | None = None
    created_at: str
    updated_at: str


class RunListResponse(BaseModel):
    runs: list[RunResponse]


class RunEventResponse(BaseModel):
    event_id: str
    run_id: str
    type: str
    timestamp: str
    payload: dict
```

- [ ] **Step 4: 实现 run service**

Create `tradingagents/api/services/runs.py`:

```python
from __future__ import annotations

import os

from fastapi import HTTPException

from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.api.schemas import CreateRunRequest
from tradingagents.llm_clients.api_key_env import get_api_key_env


class RunService:
    def __init__(self, db_path: str):
        self.runs = RunRepository(db_path)
        self.events = RunEventRepository(db_path)

    def create_run(self, request: CreateRunRequest) -> dict:
        env_var = get_api_key_env(request.llm_provider)
        if env_var and not os.getenv(env_var):
            raise HTTPException(
                status_code=400,
                detail=f"{env_var} is required for provider {request.llm_provider}",
            )
        run = self.runs.create_run(
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            asset_type=request.asset_type,
            config=request.model_dump(),
        )
        self.events.append(run["id"], "queued", {"ticker": run["ticker"]})
        return run

    def list_runs(self) -> list[dict]:
        return self.runs.list_runs()

    def get_run(self, run_id: str) -> dict:
        return self.runs.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict:
        run = self.runs.update_status(run_id, "cancel_requested")
        self.events.append(run_id, "cancel_requested", {"run_id": run_id})
        return run
```

- [ ] **Step 5: 实现 runs router 和 SSE skeleton**

Create `tradingagents/api/routers/runs.py`:

```python
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.config import ApiConfig
from tradingagents.api.schemas import CreateRunRequest, RunListResponse, RunResponse
from tradingagents.api.services.runs import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service(config: ApiConfig = Depends(get_config)) -> RunService:
    return RunService(config.db_path)


@router.post("", response_model=RunResponse, status_code=201)
def create_run(
    payload: CreateRunRequest,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.create_run(payload)


@router.get("", response_model=RunListResponse)
def list_runs(
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return {"runs": service.list_runs()}


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.get_run(run_id)


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: str,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.cancel_run(run_id)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> Response:
    after_event_id = request.headers.get("Last-Event-ID")

    async def event_stream():
        sent: set[str] = set()
        while True:
            events = service.events.list_for_run(run_id, after_event_id=after_event_id)
            for event in events:
                if event["event_id"] in sent:
                    continue
                sent.add(event["event_id"])
                yield f"id: {event['event_id']}\n"
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event)}\n\n"
            run = service.get_run(run_id)
            if run["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 6: 注册 runs router**

Modify `tradingagents/api/app.py` imports:

```python
from tradingagents.api.routers import auth, runs, settings
```

Modify router registration:

```python
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(runs.router)
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```bash
uv run --with pytest pytest tests/api/test_runs_routes.py tests/api/test_sse_events.py -q
```

Expected: PASS.

- [ ] **Step 8: 提交**

```bash
git add tradingagents/api tests/api/test_runs_routes.py tests/api/test_sse_events.py
git commit -m "feat(api): add analysis run routes"
```

---

### Task 5: RQ 队列与 fake analysis worker

**Files:**
- Create: `tradingagents/worker/__init__.py`
- Create: `tradingagents/worker/queue.py`
- Create: `tradingagents/worker/jobs.py`
- Create: `tradingagents/worker/runner.py`
- Modify: `tradingagents/api/services/runs.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: 写失败测试，验证 fake job 写入事件和完成状态**

Create `tests/worker/test_jobs.py`:

```python
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.worker.jobs import run_fake_analysis


def test_fake_analysis_job_completes_run(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run("SPY", "2026-05-19", "stock", {"ticker": "SPY"})

    run_fake_analysis(run["id"], db_path)

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])
    assert loaded["status"] == "completed"
    assert [event["type"] for event in replay] == [
        "agent_status",
        "message",
        "report_section",
        "completed",
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/worker/test_jobs.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.worker'`.

- [ ] **Step 3: 实现 worker package 和 fake job**

Create `tradingagents/worker/__init__.py`:

```python
"""Worker jobs for TradingAgents web API."""
```

Create `tradingagents/worker/jobs.py`:

```python
from __future__ import annotations

from tradingagents.api.repositories import RunEventRepository, RunRepository


def run_fake_analysis(run_id: str, db_path: str) -> None:
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    runs.update_status(run_id, "running")
    events.append(run_id, "agent_status", {"agent": "Market Analyst", "status": "running"})
    events.append(run_id, "message", {"type": "System", "content": "Fake analysis started"})
    events.append(
        run_id,
        "report_section",
        {"section": "market_report", "content": "Fake market report for local development."},
    )
    runs.update_status(run_id, "completed", result={"final_trade_decision": "Rating: Hold"})
    events.append(run_id, "completed", {"signal": "Hold"})
```

- [ ] **Step 4: 实现 RQ queue helper 和 worker runner**

Create `tradingagents/worker/queue.py`:

```python
from __future__ import annotations

from redis import Redis
from rq import Queue


DEFAULT_QUEUE_NAME = "tradingagents"


def get_queue(redis_url: str, name: str = DEFAULT_QUEUE_NAME) -> Queue:
    return Queue(name, connection=Redis.from_url(redis_url))


def enqueue_fake_analysis(redis_url: str, run_id: str, db_path: str):
    queue = get_queue(redis_url)
    return queue.enqueue("tradingagents.worker.jobs.run_fake_analysis", run_id, db_path)
```

Create `tradingagents/worker/runner.py`:

```python
from __future__ import annotations

from redis import Redis
from rq import Worker

from tradingagents.api.config import ApiConfig
from tradingagents.worker.queue import DEFAULT_QUEUE_NAME


def main() -> None:
    config = ApiConfig.from_env()
    connection = Redis.from_url(config.redis_url)
    worker = Worker([DEFAULT_QUEUE_NAME], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 暂时让 `POST /api/runs` 入队 fake job**

Modify `tradingagents/api/services/runs.py` constructor:

```python
class RunService:
    def __init__(self, db_path: str, redis_url: str | None = None):
        self.db_path = db_path
        self.redis_url = redis_url
        self.runs = RunRepository(db_path)
        self.events = RunEventRepository(db_path)
```

Modify `create_run` after queued event:

```python
        if self.redis_url:
            from tradingagents.worker.queue import enqueue_fake_analysis
            enqueue_fake_analysis(self.redis_url, run["id"], self.db_path)
        return run
```

Modify `tradingagents/api/routers/runs.py` service factory:

```python
def get_run_service(config: ApiConfig = Depends(get_config)) -> RunService:
    return RunService(config.db_path, redis_url=config.redis_url)
```

- [ ] **Step 6: 运行 worker 测试和 route 测试**

Run:

```bash
uv run --with pytest pytest tests/worker/test_jobs.py tests/api/test_runs_routes.py -q
```

Expected: Worker test PASS. Route test may fail if Redis is not running because create route enqueues. If it fails with Redis connection error, adjust RunService to accept `enqueue_enabled: bool = True` and set it false in TestClient config by adding `queue_enabled` to `ApiConfig`.

If adjustment is needed, update `ApiConfig`:

```python
queue_enabled: bool = True
```

Set from env:

```python
queue_enabled=os.getenv("TRADINGAGENTS_QUEUE_ENABLED", "true").lower() != "false",
```

Pass to `RunService`, and only enqueue when `self.queue_enabled and self.redis_url`.

- [ ] **Step 7: 提交**

```bash
git add tradingagents/worker tradingagents/api tests/worker/test_jobs.py
git commit -m "feat(worker): add queued fake analysis job"
```

---

### Task 6: 真实 TradingAgents analysis worker adapter

**Files:**
- Create: `tradingagents/worker/analysis.py`
- Modify: `tradingagents/worker/jobs.py`
- Modify: `tradingagents/worker/queue.py`
- Modify: `tradingagents/api/services/runs.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: 写失败测试，使用 fake graph 验证 adapter 写事件**

Append to `tests/worker/test_jobs.py`:

```python
from tradingagents.worker.analysis import run_analysis_with_graph


class FakeGraph:
    def __init__(self):
        self.graph = self

    def stream(self, state, **kwargs):
        yield {"market_report": "Market report", "messages": []}
        yield {"final_trade_decision": "Rating: Buy", "messages": []}


class FakePropagator:
    def create_initial_state(self, ticker, analysis_date, asset_type="stock"):
        return {"company_of_interest": ticker, "trade_date": analysis_date, "asset_type": asset_type}

    def get_graph_args(self, callbacks=None):
        return {}


def test_analysis_adapter_streams_graph_chunks(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run(
        "SPY",
        "2026-05-19",
        "stock",
        {"ticker": "SPY", "analysis_date": "2026-05-19", "asset_type": "stock"},
    )
    graph = FakeGraph()
    graph.propagator = FakePropagator()

    run_analysis_with_graph(run["id"], db_path, graph)

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])
    assert loaded["status"] == "completed"
    assert any(event["type"] == "report_section" for event in replay)
    assert replay[-1]["type"] == "completed"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/worker/test_jobs.py -q
```

Expected: FAIL because `tradingagents.worker.analysis` is missing.

- [ ] **Step 3: 实现 graph adapter**

Create `tradingagents/worker/analysis.py`:

```python
from __future__ import annotations

from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.graph.signal_processing import SignalProcessor

REPORT_KEYS = {
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
}


def run_analysis_with_graph(run_id: str, db_path: str, graph) -> None:
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.get_run(run_id)
    config = run["config"]
    ticker = config.get("ticker", run["ticker"])
    analysis_date = config.get("analysis_date", run["analysis_date"])
    asset_type = config.get("asset_type", run["asset_type"])

    runs.update_status(run_id, "running")
    events.append(run_id, "message", {"type": "System", "content": f"Analyzing {ticker} on {analysis_date}"})

    init_state = graph.propagator.create_initial_state(ticker, analysis_date, asset_type=asset_type)
    args = graph.propagator.get_graph_args()

    final_state = {}
    for chunk in graph.graph.stream(init_state, **args):
        final_state.update(chunk)
        for key in REPORT_KEYS:
            if chunk.get(key):
                events.append(run_id, "report_section", {"section": key, "content": chunk[key]})

    decision = final_state.get("final_trade_decision", "")
    signal = SignalProcessor().process_signal(decision)
    runs.update_status(run_id, "completed", result={"signal": signal, "final_trade_decision": decision})
    events.append(run_id, "completed", {"signal": signal})
```

- [ ] **Step 4: 实现真实 job function**

Append to `tradingagents/worker/jobs.py`:

```python
def run_tradingagents_analysis(run_id: str, db_path: str) -> None:
    from tradingagents.api.repositories import RunRepository
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.worker.analysis import run_analysis_with_graph

    runs = RunRepository(db_path)
    run = runs.get_run(run_id)
    config = DEFAULT_CONFIG.copy()
    run_config = run["config"]
    config["llm_provider"] = run_config["llm_provider"]
    config["quick_think_llm"] = run_config["quick_think_llm"]
    config["deep_think_llm"] = run_config["deep_think_llm"]
    config["output_language"] = run_config.get("output_language", "English")
    config["checkpoint_enabled"] = run_config.get("checkpoint_enabled", False)
    config["max_debate_rounds"] = run_config.get("research_depth", 1)
    config["max_risk_discuss_rounds"] = run_config.get("research_depth", 1)

    graph = TradingAgentsGraph(
        selected_analysts=run_config["analysts"],
        config=config,
        debug=False,
    )
    run_analysis_with_graph(run_id, db_path, graph)
```

Modify `tradingagents/worker/queue.py`:

```python
def enqueue_analysis(redis_url: str, run_id: str, db_path: str):
    queue = get_queue(redis_url)
    return queue.enqueue("tradingagents.worker.jobs.run_tradingagents_analysis", run_id, db_path)
```

Modify `tradingagents/api/services/runs.py` to enqueue real analysis instead of fake when env `TRADINGAGENTS_FAKE_ANALYSIS` is not true:

```python
            import os
            from tradingagents.worker.queue import enqueue_analysis, enqueue_fake_analysis
            if os.getenv("TRADINGAGENTS_FAKE_ANALYSIS", "false").lower() == "true":
                enqueue_fake_analysis(self.redis_url, run["id"], self.db_path)
            else:
                enqueue_analysis(self.redis_url, run["id"], self.db_path)
```

- [ ] **Step 5: 运行 worker 测试**

Run:

```bash
uv run --with pytest pytest tests/worker/test_jobs.py -q
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add tradingagents/worker tests/worker/test_jobs.py tradingagents/api/services/runs.py
git commit -m "feat(worker): add TradingAgents analysis adapter"
```

---

### Task 7: Approvals、交易安全和审计 API

**Files:**
- Modify: `tradingagents/api/repositories.py`
- Create: `tradingagents/api/services/trading.py`
- Create: `tradingagents/api/routers/approvals.py`
- Create: `tradingagents/api/routers/trades.py`
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_approvals.py`
- Test: `tests/api/test_trades_security.py`

- [ ] **Step 1: 写失败测试，验证二次确认**

Create `tests/api/test_approvals.py`:

```python
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import ApprovalRepository


def test_approval_requires_exact_confirmation(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    approvals = ApprovalRepository(db_path)
    proposal = approvals.create(
        run_id="run_1",
        ticker="AAPL",
        signal="Buy",
        side="buy",
        quantity=1.0,
        estimated_price=100.0,
        reasoning="test",
    )

    try:
        approvals.approve(proposal["id"], confirmation="APPROVE MSFT", actor="session:test")
    except ValueError as exc:
        assert "APPROVE AAPL" in str(exc)
    else:
        raise AssertionError("approval should have failed")

    approved = approvals.approve(proposal["id"], confirmation="APPROVE AAPL", actor="session:test")
    assert approved["status"] == "approved"
```

Create `tests/api/test_trades_security.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def test_manual_trade_requires_auth_and_confirmation(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    client = TestClient(create_app(config))

    denied = client.post("/api/trades/manual", json={})
    assert denied.status_code == 401

    bad_confirmation = client.post(
        "/api/trades/manual",
        headers={"Authorization": "Bearer test-token"},
        json={"ticker": "AAPL", "side": "buy", "quantity": 1, "confirmation": "BUY"},
    )
    assert bad_confirmation.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_approvals.py tests/api/test_trades_security.py -q
```

Expected: FAIL because approval repository and routes are missing.

- [ ] **Step 3: 添加 approval repository**

Append to `tradingagents/api/repositories.py`:

```python
class ApprovalRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def create(self, run_id: str | None, ticker: str, signal: str, side: str, quantity: float, estimated_price: float, reasoning: str) -> dict[str, Any]:
        approval_id = f"appr_{uuid.uuid4().hex}"
        now = utc_now()
        estimated_value = quantity * estimated_price
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO approvals
                    (id, run_id, ticker, signal, side, quantity, estimated_price, estimated_value,
                     reasoning, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (approval_id, run_id, ticker.upper(), signal, side, quantity, estimated_price,
                 estimated_value, reasoning, "pending", now, now),
            )
        return self.get(approval_id)

    def get(self, approval_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return _row_to_dict(row)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(row) for row in rows]

    def approve(self, approval_id: str, confirmation: str, actor: str) -> dict[str, Any]:
        approval = self.get(approval_id)
        expected = f"APPROVE {approval['ticker']}"
        if confirmation.strip().upper() != expected:
            raise ValueError(f"Confirmation must be exactly {expected}")
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = 'approved', updated_at = ?, decided_at = ?, decision_reason = ?
                WHERE id = ?
                """,
                (now, now, f"approved by {actor}", approval_id),
            )
        return self.get(approval_id)

    def reject(self, approval_id: str, reason: str, actor: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = 'rejected', updated_at = ?, decided_at = ?, decision_reason = ?
                WHERE id = ?
                """,
                (now, now, f"{actor}: {reason}", approval_id),
            )
        return self.get(approval_id)
```

- [ ] **Step 4: 添加 schemas 和 routes**

Append to `tradingagents/api/schemas.py`:

```python
class ApprovalDecisionRequest(BaseModel):
    confirmation: str = ""
    reason: str = ""


class ManualTradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    confirmation: str
```

Create `tradingagents/api/routers/approvals.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.repositories import ApprovalRepository, AuditRepository
from tradingagents.api.schemas import ApprovalDecisionRequest

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    status: str | None = None,
    _: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    return {"approvals": ApprovalRepository(config.db_path).list(status=status)}


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    approvals = ApprovalRepository(config.db_path)
    audit = AuditRepository(config.db_path)
    try:
        approval = approvals.approve(approval_id, payload.confirmation, actor)
    except ValueError as exc:
        audit.record("approval_failed", actor, "approval", approval_id, {"reason": str(exc)}, "rejected")
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record("approval_approved", actor, "approval", approval_id, {"ticker": approval["ticker"]}, "accepted")
    return approval


@router.post("/{approval_id}/reject")
def reject(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    approval = ApprovalRepository(config.db_path).reject(approval_id, payload.reason, actor)
    AuditRepository(config.db_path).record(
        "approval_rejected",
        actor,
        "approval",
        approval_id,
        {"reason": payload.reason},
        "accepted",
    )
    return approval
```

Create `tradingagents/api/routers/trades.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.repositories import AuditRepository
from tradingagents.api.schemas import ManualTradeRequest

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("/manual")
def manual_trade(
    payload: ManualTradeRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    expected = f"{payload.side.upper()} {payload.ticker.upper()}"
    audit = AuditRepository(config.db_path)
    if payload.confirmation.strip().upper() != expected:
        audit.record(
            "manual_trade_failed",
            actor,
            "trade",
            "manual",
            {"ticker": payload.ticker.upper(), "side": payload.side, "reason": "bad_confirmation"},
            "rejected",
        )
        raise HTTPException(status_code=400, detail=f"Confirmation must be exactly {expected}")
    audit.record(
        "manual_trade_requested",
        actor,
        "trade",
        "manual",
        {"ticker": payload.ticker.upper(), "side": payload.side, "quantity": payload.quantity},
        "accepted",
    )
    return {"status": "queued", "ticker": payload.ticker.upper(), "side": payload.side, "quantity": payload.quantity}
```

- [ ] **Step 5: 注册 routers**

Modify `tradingagents/api/app.py` imports:

```python
from tradingagents.api.routers import approvals, auth, runs, settings, trades
```

Add:

```python
    app.include_router(approvals.router)
    app.include_router(trades.router)
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run --with pytest pytest tests/api/test_approvals.py tests/api/test_trades_security.py -q
```

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add tradingagents/api tests/api/test_approvals.py tests/api/test_trades_security.py
git commit -m "feat(api): add approval and trade safety routes"
```

---

### Task 8: Portfolio、Risk、Reports API

**Files:**
- Create: `tradingagents/api/routers/portfolio.py`
- Create: `tradingagents/api/routers/risk.py`
- Create: `tradingagents/api/routers/reports.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_portfolio_routes.py`

- [ ] **Step 1: 写失败测试，验证 portfolio 空状态 API**

Create `tests/api/test_portfolio_routes.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def make_client(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(config))


def test_portfolio_account_returns_mock_account(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/portfolio/account", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["cash"] >= 0
    assert body["equity"] >= 0


def test_risk_status_returns_limits(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/risk/status", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert "limits" in response.json()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run --with pytest pytest tests/api/test_portfolio_routes.py -q
```

Expected: FAIL because routes are missing.

- [ ] **Step 3: 实现 portfolio router**

Create `tradingagents/api/routers/portfolio.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingbot.broker.mock import MockBroker
from tradingbot.portfolio.database import PortfolioDatabase
from tradingbot.portfolio.manager import PortfolioManager

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _manager(config: ApiConfig) -> tuple[MockBroker, PortfolioManager]:
    broker = MockBroker(starting_cash=100_000.0)
    db = PortfolioDatabase(config.db_path)
    return broker, PortfolioManager(broker, db)


@router.get("/account")
def account(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    broker, _ = _manager(config)
    account_info = broker.get_account()
    return account_info.__dict__


@router.get("/positions")
def positions(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    broker, _ = _manager(config)
    return {"positions": [position.__dict__ for position in broker.get_positions()]}


@router.get("/snapshots")
def snapshots(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    db = PortfolioDatabase(config.db_path)
    return {"snapshots": [snapshot.__dict__ for snapshot in db.get_snapshots()]}


@router.get("/performance")
def performance(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    broker, manager = _manager(config)
    metrics = manager.get_performance_metrics()
    return metrics.__dict__
```

- [ ] **Step 4: 实现 risk router**

Create `tradingagents/api/routers/risk.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from tradingagents.api.deps import require_auth
from tradingbot.config import TRADINGBOT_CONFIG

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/limits")
def limits(_: str = Depends(require_auth)) -> dict:
    return {
        "max_single_position_pct": TRADINGBOT_CONFIG.get("max_single_position_pct", 0.10),
        "max_total_exposure_pct": TRADINGBOT_CONFIG.get("max_total_exposure_pct", 0.80),
        "daily_loss_limit_pct": TRADINGBOT_CONFIG.get("daily_loss_limit_pct", -0.02),
        "min_cash_reserve": TRADINGBOT_CONFIG.get("min_cash_reserve", 1000.0),
    }


@router.get("/status")
def status(_: str = Depends(require_auth)) -> dict:
    return {
        "circuit_breaker": {"active": False, "reason": None},
        "limits": limits(_),
    }
```

- [ ] **Step 5: 实现 reports router**

Create `tradingagents/api/routers/reports.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    root = Path(config.results_dir)
    reports = []
    if root.exists():
        for path in root.glob("**/complete_report.md"):
            reports.append({"id": str(path.relative_to(root)), "path": str(path)})
    return {"reports": reports}
```

- [ ] **Step 6: 注册 routers 并测试**

Modify `tradingagents/api/app.py`:

```python
from tradingagents.api.routers import approvals, auth, portfolio, reports, risk, runs, settings, trades
```

Add:

```python
    app.include_router(portfolio.router)
    app.include_router(reports.router)
    app.include_router(risk.router)
```

Run:

```bash
uv run --with pytest pytest tests/api/test_portfolio_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add tradingagents/api tests/api/test_portfolio_routes.py
git commit -m "feat(api): add portfolio risk and reports routes"
```

---

### Task 9: React 项目脚手架与基础测试

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/index.html`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/index.css`
- Test: `apps/web/src/App.test.tsx`

- [ ] **Step 1: 创建 React 项目文件**

Create `apps/web/package.json`:

```json
{
  "name": "tradingagents-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.80.0",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.6.3",
    "vite": "^6.0.0",
    "vitest": "^2.1.8"
  }
}
```

Create `apps/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TradingAgents</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `apps/web/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

Create `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": []
}
```

Create `apps/web/src/index.css`:

```css
:root {
  color: #e5e7eb;
  background: #111827;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
}

button,
input,
select {
  font: inherit;
}
```

Create `apps/web/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./index.css";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

Create `apps/web/src/App.tsx`:

```tsx
export function App() {
  return (
    <main style={{ minHeight: "100vh", padding: 24 }}>
      <h1>TradingAgents</h1>
      <p>React web frontend is ready.</p>
    </main>
  );
}
```

Create `apps/web/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 2: 写基础测试**

Create `apps/web/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the TradingAgents shell", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "TradingAgents" })).toBeInTheDocument();
});
```

- [ ] **Step 3: 安装并测试**

Run:

```bash
cd apps/web && npm install && npm test
```

Expected: PASS.

- [ ] **Step 4: 构建验证**

Run:

```bash
cd apps/web && npm run build
```

Expected: PASS and `dist/` generated.

- [ ] **Step 5: 提交**

```bash
git add apps/web
git commit -m "feat(web): scaffold React frontend"
```

---

### Task 10: 前端 API client、认证页和 AppShell

**Files:**
- Create: `apps/web/src/lib/api/types.ts`
- Create: `apps/web/src/lib/api/client.ts`
- Create: `apps/web/src/components/auth/LoginPage.tsx`
- Create: `apps/web/src/components/layout/AppShell.tsx`
- Modify: `apps/web/src/App.tsx`
- Test: `apps/web/src/lib/api/client.test.ts`

- [ ] **Step 1: 写 API client 测试**

Create `apps/web/src/lib/api/client.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";

describe("ApiClient", () => {
  it("adds bearer token to requests", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ authenticated: true }),
    });
    const client = new ApiClient("/api", () => "abc", fetcher as unknown as typeof fetch);

    await client.get("/auth/me");

    expect(fetcher).toHaveBeenCalledWith("/api/auth/me", {
      headers: { Authorization: "Bearer abc" },
    });
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd apps/web && npm test -- src/lib/api/client.test.ts
```

Expected: FAIL because client file is missing.

- [ ] **Step 3: 实现 API types 和 client**

Create `apps/web/src/lib/api/types.ts`:

```ts
export type SettingsResponse = {
  auth_enabled: boolean;
  broker: string;
  paper_trading: boolean;
  db_path: string;
  results_dir: string;
  provider_keys: Record<string, { configured: boolean }>;
  watchlist: string[];
  risk_limits: Record<string, number>;
  scheduler: Record<string, string>;
};

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "stale";

export type Run = {
  id: string;
  ticker: string;
  analysis_date: string;
  asset_type: string;
  status: RunStatus;
  config: Record<string, unknown>;
  error?: string | null;
  result?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
```

Create `apps/web/src/lib/api/client.ts`:

```ts
export class ApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getToken: () => string | null,
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  async get<T>(path: string): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      headers: this.headers(),
    });
    return this.parse<T>(response);
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers() },
      body: JSON.stringify(body),
    });
    return this.parse<T>(response);
  }

  private headers(): Record<string, string> {
    const token = this.getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  }
}
```

- [ ] **Step 4: 实现 LoginPage 和 AppShell**

Create `apps/web/src/components/auth/LoginPage.tsx`:

```tsx
import { FormEvent, useState } from "react";

type LoginPageProps = {
  onLogin: (token: string) => void;
};

export function LoginPage({ onLogin }: LoginPageProps) {
  const [token, setToken] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (token.trim()) {
      onLogin(token.trim());
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <form onSubmit={submit} style={{ width: 360, display: "grid", gap: 12 }}>
        <h1>TradingAgents</h1>
        <label>
          Access Token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <button type="submit">Login</button>
      </form>
    </main>
  );
}
```

Create `apps/web/src/components/layout/AppShell.tsx`:

```tsx
import { NavLink, Outlet } from "react-router-dom";

const nav = [
  ["Workbench", "/"],
  ["Runs", "/runs"],
  ["Portfolio", "/portfolio"],
  ["Performance", "/performance"],
  ["Trades", "/trades"],
  ["Risk", "/risk"],
  ["Approvals", "/approvals"],
  ["Settings", "/settings"],
] as const;

export function AppShell() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", minHeight: "100vh" }}>
      <aside style={{ borderRight: "1px solid #374151", padding: 16 }}>
        <h1>TradingAgents</h1>
        <nav style={{ display: "grid", gap: 8 }}>
          {nav.map(([label, to]) => (
            <NavLink key={to} to={to}>
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <section style={{ padding: 24 }}>
        <Outlet />
      </section>
    </div>
  );
}
```

Modify `apps/web/src/App.tsx`:

```tsx
import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./components/auth/LoginPage";
import { AppShell } from "./components/layout/AppShell";

function Placeholder({ title }: { title: string }) {
  return <h2>{title}</h2>;
}

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem("ta_token"));

  if (!token) {
    return (
      <LoginPage
        onLogin={(nextToken) => {
          localStorage.setItem("ta_token", nextToken);
          setToken(nextToken);
        }}
      />
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Placeholder title="Workbench" />} />
        <Route path="/runs" element={<Placeholder title="Runs" />} />
        <Route path="/portfolio" element={<Placeholder title="Portfolio" />} />
        <Route path="/performance" element={<Placeholder title="Performance" />} />
        <Route path="/trades" element={<Placeholder title="Trades" />} />
        <Route path="/risk" element={<Placeholder title="Risk" />} />
        <Route path="/approvals" element={<Placeholder title="Approvals" />} />
        <Route path="/settings" element={<Placeholder title="Settings" />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 5: 更新 App 测试以处理 login**

Modify `apps/web/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";

it("renders login when no token exists", () => {
  localStorage.clear();
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  expect(screen.getByRole("heading", { name: "TradingAgents" })).toBeInTheDocument();
  expect(screen.getByLabelText("Access Token")).toBeInTheDocument();
});
```

- [ ] **Step 6: 测试与提交**

Run:

```bash
cd apps/web && npm test && npm run build
```

Expected: PASS.

Commit:

```bash
git add apps/web
git commit -m "feat(web): add auth shell and API client"
```

---

### Task 11: Run event reducer、Workbench 和 Run detail

**Files:**
- Create: `apps/web/src/lib/runs/eventReducer.ts`
- Create: `apps/web/src/lib/runs/eventReducer.test.ts`
- Create: `apps/web/src/pages/WorkbenchPage.tsx`
- Create: `apps/web/src/pages/RunsPage.tsx`
- Create: `apps/web/src/pages/RunDetailPage.tsx`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: 写 reducer 测试**

Create `apps/web/src/lib/runs/eventReducer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { reduceRunEvent } from "./eventReducer";

describe("reduceRunEvent", () => {
  it("tracks agent status and report sections", () => {
    let state = reduceRunEvent(undefined, {
      event_id: "evt_1",
      run_id: "run_1",
      type: "agent_status",
      timestamp: "2026-05-19T00:00:00Z",
      payload: { agent: "Market Analyst", status: "running" },
    });
    state = reduceRunEvent(state, {
      event_id: "evt_2",
      run_id: "run_1",
      type: "report_section",
      timestamp: "2026-05-19T00:00:01Z",
      payload: { section: "market_report", content: "Market report" },
    });

    expect(state.agentStatus["Market Analyst"]).toBe("running");
    expect(state.reportSections.market_report).toBe("Market report");
  });
});
```

- [ ] **Step 2: 实现 reducer**

Create `apps/web/src/lib/runs/eventReducer.ts`:

```ts
export type RunEvent = {
  event_id: string;
  run_id: string;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export type RunEventState = {
  agentStatus: Record<string, string>;
  messages: Array<{ type: string; content: string; timestamp: string }>;
  reportSections: Record<string, string>;
  completed: boolean;
  failed?: string;
};

const initialState: RunEventState = {
  agentStatus: {},
  messages: [],
  reportSections: {},
  completed: false,
};

export function reduceRunEvent(state: RunEventState = initialState, event: RunEvent): RunEventState {
  if (event.type === "agent_status") {
    const agent = String(event.payload.agent);
    const status = String(event.payload.status);
    return { ...state, agentStatus: { ...state.agentStatus, [agent]: status } };
  }
  if (event.type === "message") {
    return {
      ...state,
      messages: [
        ...state.messages,
        {
          type: String(event.payload.type ?? "System"),
          content: String(event.payload.content ?? ""),
          timestamp: event.timestamp,
        },
      ],
    };
  }
  if (event.type === "report_section") {
    return {
      ...state,
      reportSections: {
        ...state.reportSections,
        [String(event.payload.section)]: String(event.payload.content ?? ""),
      },
    };
  }
  if (event.type === "completed") {
    return { ...state, completed: true };
  }
  if (event.type === "failed") {
    return { ...state, failed: String(event.payload.error ?? "Run failed") };
  }
  return state;
}
```

- [ ] **Step 3: 实现 Workbench 和 Runs 页面**

Create `apps/web/src/pages/WorkbenchPage.tsx`:

```tsx
export function WorkbenchPage() {
  return (
    <section>
      <h2>Analysis Workbench</h2>
      <form style={{ display: "grid", gap: 12, maxWidth: 640 }}>
        <label>
          Ticker
          <input defaultValue="SPY" />
        </label>
        <label>
          Analysis Date
          <input type="date" />
        </label>
        <label>
          Provider
          <select defaultValue="openai">
            <option value="openai">OpenAI</option>
            <option value="ollama">Ollama</option>
          </select>
        </label>
        <button type="button">Create Run</button>
      </form>
    </section>
  );
}
```

Create `apps/web/src/pages/RunsPage.tsx`:

```tsx
export function RunsPage() {
  return (
    <section>
      <h2>Runs</h2>
      <p>Historical analysis runs will appear here.</p>
    </section>
  );
}
```

Create `apps/web/src/pages/RunDetailPage.tsx`:

```tsx
export function RunDetailPage() {
  return (
    <section>
      <h2>Run Detail</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <h3>Agent Status</h3>
          <p>No events loaded.</p>
        </div>
        <div>
          <h3>Current Report</h3>
          <p>No report sections loaded.</p>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Wire routes**

Modify `apps/web/src/App.tsx` imports:

```tsx
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
```

Replace the temporary route elements:

```tsx
        <Route index element={<WorkbenchPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
```

- [ ] **Step 5: 测试与提交**

Run:

```bash
cd apps/web && npm test && npm run build
```

Expected: PASS.

Commit:

```bash
git add apps/web
git commit -m "feat(web): add run workbench skeleton"
```

---

### Task 12: Portfolio、Performance、Trades、Risk、Approvals、Settings 页面骨架

**Files:**
- Create: `apps/web/src/pages/PortfolioPage.tsx`
- Create: `apps/web/src/pages/PerformancePage.tsx`
- Create: `apps/web/src/pages/TradesPage.tsx`
- Create: `apps/web/src/pages/RiskPage.tsx`
- Create: `apps/web/src/pages/ApprovalsPage.tsx`
- Create: `apps/web/src/pages/SettingsPage.tsx`
- Modify: `apps/web/src/App.tsx`
- Test: `apps/web/src/pages/ApprovalsPage.test.tsx`

- [ ] **Step 1: 写 Approvals 页面测试**

Create `apps/web/src/pages/ApprovalsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { ApprovalsPage } from "./ApprovalsPage";

it("renders approvals heading and confirmation hint", () => {
  render(<ApprovalsPage />);
  expect(screen.getByRole("heading", { name: "Approvals" })).toBeInTheDocument();
  expect(screen.getByText(/APPROVE/)).toBeInTheDocument();
});
```

- [ ] **Step 2: 创建页面骨架**

Create `apps/web/src/pages/PortfolioPage.tsx`:

```tsx
export function PortfolioPage() {
  return (
    <section>
      <h2>Portfolio</h2>
      <div>Account KPIs, positions, and allocation chart will render here.</div>
    </section>
  );
}
```

Create `apps/web/src/pages/PerformancePage.tsx`:

```tsx
export function PerformancePage() {
  return (
    <section>
      <h2>Performance</h2>
      <div>Equity curve, drawdown, and daily P&L will render here.</div>
    </section>
  );
}
```

Create `apps/web/src/pages/TradesPage.tsx`:

```tsx
export function TradesPage() {
  return (
    <section>
      <h2>Trades</h2>
      <div>Trade history, closed positions, and reasoning links will render here.</div>
    </section>
  );
}
```

Create `apps/web/src/pages/RiskPage.tsx`:

```tsx
export function RiskPage() {
  return (
    <section>
      <h2>Risk</h2>
      <div>Circuit breaker, exposure, cash reserve, and concentration will render here.</div>
    </section>
  );
}
```

Create `apps/web/src/pages/ApprovalsPage.tsx`:

```tsx
export function ApprovalsPage() {
  return (
    <section>
      <h2>Approvals</h2>
      <p>Pending automated trade proposals require confirmation like APPROVE AAPL.</p>
    </section>
  );
}
```

Create `apps/web/src/pages/SettingsPage.tsx`:

```tsx
export function SettingsPage() {
  return (
    <section>
      <h2>Settings</h2>
      <div>Backend environment, broker mode, provider keys, and risk limits will render here.</div>
    </section>
  );
}
```

- [ ] **Step 3: Wire routes**

Modify `apps/web/src/App.tsx` imports:

```tsx
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { PerformancePage } from "./pages/PerformancePage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { RiskPage } from "./pages/RiskPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TradesPage } from "./pages/TradesPage";
```

Replace the temporary route elements:

```tsx
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/performance" element={<PerformancePage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/risk" element={<RiskPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
```

- [ ] **Step 4: 测试与提交**

Run:

```bash
cd apps/web && npm test && npm run build
```

Expected: PASS.

Commit:

```bash
git add apps/web
git commit -m "feat(web): add dashboard page skeletons"
```

---

### Task 13: Docker Compose 和运行文档

**Files:**
- Modify: `docker-compose.yml`
- Create: `docs/web-development.md`
- Modify: `README.md`

- [ ] **Step 1: 修改 docker-compose**

Modify `docker-compose.yml` to include services:

```yaml
services:
  redis:
    image: redis:7
    ports:
      - "6379:6379"

  api:
    build: .
    command: uvicorn tradingagents.api.app:app --host 0.0.0.0 --port 8000
    environment:
      TRADINGAGENTS_REDIS_URL: redis://redis:6379/0
      TRADINGAGENTS_API_TOKEN: ${TRADINGAGENTS_API_TOKEN:-dev-token}
    ports:
      - "8000:8000"
    depends_on:
      - redis

  worker:
    build: .
    command: python -m tradingagents.worker.runner
    environment:
      TRADINGAGENTS_REDIS_URL: redis://redis:6379/0
      TRADINGAGENTS_API_TOKEN: ${TRADINGAGENTS_API_TOKEN:-dev-token}
    depends_on:
      - redis

  web:
    image: node:22
    working_dir: /app/apps/web
    command: sh -c "npm install && npm run dev"
    volumes:
      - .:/app
    ports:
      - "5173:5173"
    depends_on:
      - api
```

If the existing compose file already contains a `tradingagents` service, preserve it and append these services without deleting current CLI/Docker behavior.

- [ ] **Step 2: 创建开发文档**

Create `docs/web-development.md`:

~~~markdown
# Web Development

## Services

- React frontend: `apps/web`
- FastAPI backend: `tradingagents.api.app:app`
- Worker: `python -m tradingagents.worker.runner`
- Queue: Redis

## Local Development

Install Python dependencies:

```bash
uv sync --python /usr/local/bin/python3.13
```

Run API:

```bash
uv run uvicorn tradingagents.api.app:app --reload --port 8000
```

Run worker:

```bash
uv run python -m tradingagents.worker.runner
```

Run frontend:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`.

## Authentication

Set `TRADINGAGENTS_API_TOKEN` in `.env`. Use that token in the web login screen.

## Safe Defaults

Use `TRADINGBOT_BROKER=mock` while developing. Do not enable live broker credentials until manual trade and approval audit paths have been verified.
~~~

- [ ] **Step 3: 更新 README 简短入口**

Append a short section to `README.md`:

```markdown
## Web App Development

The React/FastAPI web app is being introduced alongside the existing CLI and Streamlit dashboard.
See [docs/web-development.md](docs/web-development.md) for local API, worker, Redis, and frontend commands.
```

- [ ] **Step 4: 验证 compose config**

Run:

```bash
docker compose config
```

Expected: command exits 0 and prints merged compose config.

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml docs/web-development.md README.md
git commit -m "docs: add web app development workflow"
```

---

## Final Verification

- [ ] Run backend tests:

```bash
uv run --with pytest pytest tests/api tests/worker -q
```

Expected: all new backend and worker tests pass.

- [ ] Run existing tests:

```bash
uv run --with pytest pytest -q
```

Expected: existing suite remains green except live-provider skips guarded by env vars.

- [ ] Run frontend tests and build:

```bash
cd apps/web && npm test && npm run build
```

Expected: tests pass and Vite build succeeds.

- [ ] Run API health manually:

```bash
uv run uvicorn tradingagents.api.app:app --port 8000
```

Expected: `GET http://localhost:8000/api/health` returns `{"status":"ok"}`.

- [ ] Run frontend dev server:

```bash
cd apps/web && npm run dev
```

Expected: app opens at `http://localhost:5173`, shows login, and sidebar after token entry.

## Self-Review

- Spec coverage: this plan covers FastAPI, worker/queue, SQLite persistence, auth, settings, runs/events, approvals/trade safety, portfolio/risk/reports API, React scaffold, React pages, and Docker/docs.
- Intentional deferral: rich chart rendering, full shadcn styling, and real broker execution are introduced after the skeleton/API contracts are in place. The safety gates and audit records are planned before any real execution UI is completed.
- Red-flag scan: no task uses unresolved marker text or deferred-implementation wording as an instruction.
- Type consistency: run ids use `run_*`, event ids use `evt_*`, approval ids use `appr_*`, audit ids use `aud_*`; API response field names match repository output names.
