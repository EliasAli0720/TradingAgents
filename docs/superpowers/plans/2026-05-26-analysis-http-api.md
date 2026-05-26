# Analysis HTTP API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deployable FastAPI + Celery + Redis + PostgreSQL HTTP service for asynchronous TradingAgents multi-agent analysis.

**Architecture:** FastAPI creates and serves analysis run records; Celery workers execute `TradingAgentsGraph.propagate()`; PostgreSQL stores run metadata, events, and results. Redis is used only as Celery broker/result backend. The first version exposes analysis only and has no application-layer authentication.

**Tech Stack:** FastAPI, Celery, Redis, SQLAlchemy, PostgreSQL via `psycopg`, native FastAPI `StreamingResponse`, pytest, FastAPI `TestClient`.

---

## File Structure

Create or modify these files:

- Modify: `pyproject.toml`
  - Add API/worker dependencies.
  - Add test/dev dependency group so `python -m pytest` is available.
  - Include `tradingagents.api*` and `tradingagents.worker*` through package discovery.
- Create: `tradingagents/api/__init__.py`
  - Package marker.
- Create: `tradingagents/api/config.py`
  - Read `DATABASE_URL`, `REDIS_URL`, and API task settings from environment.
- Create: `tradingagents/api/db.py`
  - SQLAlchemy engine/session/Base creation helpers.
  - `init_db()` schema bootstrap for first-version deployment.
- Create: `tradingagents/api/models.py`
  - SQLAlchemy models for `analysis_runs`, `analysis_run_events`, and `analysis_run_results`.
- Create: `tradingagents/api/schemas.py`
  - Pydantic request/response schemas and request validation.
- Create: `tradingagents/api/repositories.py`
  - Persistence operations used by both FastAPI routes and Celery worker.
- Create: `tradingagents/api/serialization.py`
  - JSON-safe final-state/report extraction helpers.
- Create: `tradingagents/api/deps.py`
  - FastAPI dependency helpers for DB sessions and task enqueueing.
- Create: `tradingagents/api/routers/__init__.py`
  - Router package marker.
- Create: `tradingagents/api/routers/health.py`
  - `GET /health`.
- Create: `tradingagents/api/routers/runs.py`
  - `POST /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/result`, `GET /runs/{run_id}/events`.
- Create: `tradingagents/api/app.py`
  - FastAPI app factory and module-level `app`.
- Create: `tradingagents/worker/__init__.py`
  - Package marker.
- Create: `tradingagents/worker/celery_app.py`
  - Celery app configured from API settings.
- Create: `tradingagents/worker/analysis.py`
  - TradingAgents execution wrapper.
- Create: `tradingagents/worker/jobs.py`
  - Celery task implementation.
- Create: `tests/api/test_schemas.py`
  - Request validation tests.
- Create: `tests/api/test_repositories.py`
  - Repository persistence tests.
- Create: `tests/api/test_runs_routes.py`
  - FastAPI route tests.
- Create: `tests/api/test_sse_events.py`
  - SSE historical event test.
- Create: `tests/api/test_health.py`
  - Health route test.
- Create: `tests/worker/test_jobs.py`
  - Worker success/failure tests with fake analysis executor.

Do not edit or rely on the existing `__pycache__` files under `tradingagents/api`, `tradingagents/worker`, `tests/api`, or `tests/worker`.

---

## Task 1: Dependencies, Packaging, and Test Runner

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing verification**

Run:

```bash
python -m pytest --version
```

Expected before this task: FAIL with `No module named pytest` in the current environment.

- [ ] **Step 2: Add runtime and dev dependencies**

Modify `pyproject.toml`:

```toml
dependencies = [
    "langchain-core>=0.3.81",
    "backtrader>=1.9.78.123",
    "langchain-anthropic>=0.3.15",
    "langchain-experimental>=0.3.4",
    "langchain-google-genai>=4.0.0",
    "langchain-openai>=0.3.23",
    "langgraph>=0.4.8",
    "langgraph-checkpoint-sqlite>=2.0.0",
    "pandas>=2.3.0",
    "parsel>=1.10.0",
    "pytz>=2025.2",
    "questionary>=2.1.0",
    "redis>=6.2.0",
    "requests>=2.32.4",
    "rich>=14.0.0",
    "typer>=0.21.0",
    "setuptools>=80.9.0",
    "stockstats>=0.6.5",
    "tqdm>=4.67.1",
    "typing-extensions>=4.14.0",
    "yfinance>=0.2.63",
    "alpaca-py>=0.38.0",
    "apscheduler>=3.10.0",
    "streamlit>=1.45.0",
    "plotly>=6.0.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "celery>=5.4.0",
    "sqlalchemy>=2.0.0",
    "psycopg[binary]>=3.2.0",
    "httpx>=0.28.0",
    "pytest>=8.0.0",
]
```

Modify package discovery:

```toml
[tool.setuptools.packages.find]
include = ["tradingagents*", "tradingbot*", "cli*"]
```

Rationale:

- `httpx` is required by FastAPI `TestClient`.
- `pytest` is added to make the existing test suite runnable from a clean install.
- `tradingbot*` is included because the current branch already contains `tradingbot/`, and package discovery currently omits it.

- [ ] **Step 3: Sync/install dependencies**

Run:

```bash
uv sync
```

Expected: dependency resolution succeeds and installs pytest/API packages.

- [ ] **Step 4: Verify pytest is available**

Run:

```bash
python -m pytest --version
```

Expected: PASS, prints pytest version.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add analysis api dependencies"
```

---

## Task 2: Database Models and Session Helpers

**Files:**
- Create: `tradingagents/api/__init__.py`
- Create: `tradingagents/api/config.py`
- Create: `tradingagents/api/db.py`
- Create: `tradingagents/api/models.py`
- Test: `tests/api/test_repositories.py`

- [ ] **Step 1: Write failing model/schema persistence tests**

Create `tests/api/test_repositories.py`:

```python
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base
from tradingagents.api.models import AnalysisRun, AnalysisRunEvent, AnalysisRunResult


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_analysis_tables_can_store_run_event_and_result():
    session = _session()
    now = datetime.now(timezone.utc)
    run = AnalysisRun(
        run_id="run_test",
        status="queued",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market", "news"],
        current_step=None,
        celery_task_id=None,
        error=None,
        created_at=now,
    )
    session.add(run)
    session.add(AnalysisRunEvent(
        run_id="run_test",
        event_type="run_queued",
        payload={"run_id": "run_test", "status": "queued"},
        created_at=now,
    ))
    session.add(AnalysisRunResult(
        run_id="run_test",
        decision="Hold",
        reports={"final_trade_decision": "Rating: Hold"},
        final_state={"company_of_interest": "NVDA"},
        created_at=now,
    ))
    session.commit()

    saved = session.get(AnalysisRun, "run_test")
    assert saved.ticker == "NVDA"
    assert saved.analysts == ["market", "news"]
    assert session.query(AnalysisRunEvent).one().event_type == "run_queued"
    assert session.get(AnalysisRunResult, "run_test").decision == "Hold"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/api/test_repositories.py::test_analysis_tables_can_store_run_event_and_result -q
```

Expected: FAIL because `tradingagents.api.db` and `tradingagents.api.models` do not exist.

- [ ] **Step 3: Implement config, Base, and models**

Create `tradingagents/api/__init__.py`:

```python
"""HTTP API package for TradingAgents analysis service."""
```

Create `tradingagents/api/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    redis_url: str
    task_time_limit_seconds: int = 3600


def get_api_settings() -> ApiSettings:
    return ApiSettings(
        database_url=os.environ.get("DATABASE_URL", "sqlite+pysqlite:///./tradingagents_api.db"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        task_time_limit_seconds=int(
            os.environ.get("TRADINGAGENTS_API_TASK_TIME_LIMIT_SECONDS", "3600")
        ),
    )
```

Create `tradingagents/api/db.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from tradingagents.api.config import get_api_settings


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str | None = None):
    url = database_url or get_api_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from tradingagents.api import models  # noqa: F401
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
```

Create `tradingagents/api/models.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from tradingagents.api.db import Base


JsonType = JSON().with_variant(JSONB, "postgresql")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    analysts: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    current_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_analysis_runs_created_at", "created_at"),
        Index("idx_analysis_runs_ticker_trade_date", "ticker", "trade_date"),
    )


class AnalysisRunEvent(Base):
    __tablename__ = "analysis_run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_analysis_run_events_run_id_id", "run_id", "id"),
        Index("idx_analysis_run_events_created_at", "created_at"),
    )


class AnalysisRunResult(Base):
    __tablename__ = "analysis_run_results"

    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reports: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    final_state: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Run test to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_repositories.py::test_analysis_tables_can_store_run_event_and_result -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api tests/api/test_repositories.py
git commit -m "feat(api): add analysis persistence models"
```

---

## Task 3: Request and Response Schemas

**Files:**
- Create: `tradingagents/api/schemas.py`
- Test: `tests/api/test_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/api/test_schemas.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from tradingagents.api.schemas import CreateRunRequest


def test_create_run_request_normalizes_ticker():
    req = CreateRunRequest(
        ticker="nvda",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market", "news"],
    )
    assert req.ticker == "NVDA"


def test_create_run_request_rejects_invalid_ticker():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="../NVDA",
            trade_date=date(2026, 1, 15),
            asset_type="stock",
            analysts=["market"],
        )


def test_create_run_request_rejects_future_date():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="NVDA",
            trade_date=date.today() + timedelta(days=1),
            asset_type="stock",
            analysts=["market"],
        )


def test_create_run_request_rejects_crypto_fundamentals():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="BTC-USD",
            trade_date=date(2026, 1, 15),
            asset_type="crypto",
            analysts=["market", "fundamentals"],
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/api/test_schemas.py -q
```

Expected: FAIL because `tradingagents.api.schemas` does not exist.

- [ ] **Step 3: Implement schemas**

Create `tradingagents/api/schemas.py`:

```python
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


RunStatus = Literal["queued", "running", "succeeded", "failed"]
AssetType = Literal["stock", "crypto"]
AnalystKey = Literal["market", "social", "news", "fundamentals"]

_TICKER_RE = re.compile(r"^[A-Z0-9._\\-^]{1,32}$")


class CreateRunRequest(BaseModel):
    ticker: str
    trade_date: date
    asset_type: AssetType = "stock"
    analysts: list[AnalystKey] = Field(default_factory=lambda: ["market", "social", "news", "fundamentals"])

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not _TICKER_RE.match(ticker):
            raise ValueError("ticker must be 1-32 chars using A-Z, 0-9, '.', '_', '-', '^'")
        return ticker

    @field_validator("trade_date")
    @classmethod
    def reject_future_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("trade_date cannot be in the future")
        return value

    @field_validator("analysts")
    @classmethod
    def require_analysts(cls, value: list[AnalystKey]) -> list[AnalystKey]:
        if not value:
            raise ValueError("at least one analyst is required")
        return value

    @model_validator(mode="after")
    def reject_crypto_fundamentals(self):
        if self.asset_type == "crypto" and "fundamentals" in self.analysts:
            raise ValueError("fundamentals analyst is not supported for crypto assets")
        return self


class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatus
    ticker: str
    trade_date: date
    asset_type: AssetType
    analysts: list[AnalystKey]
    current_step: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]


class RunResultResponse(BaseModel):
    run_id: str
    status: Literal["succeeded"]
    decision: str
    reports: dict[str, Any]
    final_state: dict[str, Any]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    postgres: str
    redis: str
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_schemas.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/schemas.py tests/api/test_schemas.py
git commit -m "feat(api): add run request schemas"
```

---

## Task 4: Repository Layer

**Files:**
- Create: `tradingagents/api/repositories.py`
- Modify: `tests/api/test_repositories.py`

- [ ] **Step 1: Add failing repository tests**

Append to `tests/api/test_repositories.py`:

```python
from tradingagents.api.repositories import AnalysisRunRepository


def test_repository_creates_run_and_queued_event():
    session = _session()
    repo = AnalysisRunRepository(session)

    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    session.commit()

    assert run.run_id.startswith("run_")
    assert run.status == "queued"
    events = repo.list_events(run.run_id)
    assert [event.event_type for event in events] == ["run_queued"]


def test_repository_stores_success_result():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)
    repo.store_success(
        run_id=run.run_id,
        decision="Hold",
        reports={"final_trade_decision": "Rating: Hold"},
        final_state={"company_of_interest": "NVDA"},
    )
    session.commit()

    saved = repo.get_run(run.run_id)
    result = repo.get_result(run.run_id)
    assert saved.status == "succeeded"
    assert saved.current_step == "Completed"
    assert result.decision == "Hold"
    assert repo.list_events(run.run_id)[-1].event_type == "run_succeeded"


def test_repository_stores_failure():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)
    repo.store_failure(run.run_id, "provider failed")
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "provider failed"
    assert repo.list_events(run.run_id)[-1].event_type == "run_failed"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/api/test_repositories.py -q
```

Expected: FAIL because `AnalysisRunRepository` does not exist.

- [ ] **Step 3: Implement repository**

Create `tradingagents/api/repositories.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun, AnalysisRunEvent, AnalysisRunResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id() -> str:
    return f"run_{uuid4().hex}"


class AnalysisRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(
        self,
        ticker: str,
        trade_date: date,
        asset_type: str,
        analysts: list[str],
    ) -> AnalysisRun:
        now = utcnow()
        run = AnalysisRun(
            run_id=new_run_id(),
            status="queued",
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            analysts=analysts,
            current_step=None,
            celery_task_id=None,
            error=None,
            created_at=now,
        )
        self.session.add(run)
        self.add_event(run.run_id, "run_queued", {"run_id": run.run_id, "status": "queued"})
        return run

    def get_run(self, run_id: str) -> Optional[AnalysisRun]:
        return self.session.get(AnalysisRun, run_id)

    def set_celery_task_id(self, run_id: str, task_id: str) -> None:
        run = self.require_run(run_id)
        run.celery_task_id = task_id

    def require_run(self, run_id: str) -> AnalysisRun:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def mark_running(self, run_id: str) -> AnalysisRun:
        run = self.require_run(run_id)
        run.status = "running"
        run.started_at = utcnow()
        run.current_step = "Analysis running"
        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
        return run

    def store_success(
        self,
        run_id: str,
        decision: str,
        reports: dict[str, Any],
        final_state: dict[str, Any],
    ) -> AnalysisRunResult:
        now = utcnow()
        run = self.require_run(run_id)
        result = AnalysisRunResult(
            run_id=run_id,
            decision=decision,
            reports=reports,
            final_state=final_state,
            created_at=now,
        )
        self.session.merge(result)
        run.status = "succeeded"
        run.finished_at = now
        run.current_step = "Completed"
        run.error = None
        self.add_event(run_id, "run_succeeded", {"run_id": run_id, "decision": decision})
        return result

    def store_failure(self, run_id: str, error: str) -> None:
        run = self.require_run(run_id)
        run.status = "failed"
        run.finished_at = utcnow()
        run.current_step = "Failed"
        run.error = error
        self.add_event(run_id, "run_failed", {"run_id": run_id, "error": error})

    def get_result(self, run_id: str) -> Optional[AnalysisRunResult]:
        return self.session.get(AnalysisRunResult, run_id)

    def add_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> AnalysisRunEvent:
        event = AnalysisRunEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at=utcnow(),
        )
        self.session.add(event)
        return event

    def list_events(self, run_id: str, after_id: int = 0) -> list[AnalysisRunEvent]:
        stmt = (
            select(AnalysisRunEvent)
            .where(AnalysisRunEvent.run_id == run_id, AnalysisRunEvent.id > after_id)
            .order_by(AnalysisRunEvent.id.asc())
        )
        return list(self.session.scalars(stmt))
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_repositories.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/repositories.py tests/api/test_repositories.py
git commit -m "feat(api): add run repository"
```

---

## Task 5: Analysis Serialization and Execution Wrapper

**Files:**
- Create: `tradingagents/api/serialization.py`
- Create: `tradingagents/worker/__init__.py`
- Create: `tradingagents/worker/analysis.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write failing serialization tests**

Create `tests/worker/test_jobs.py`:

```python
from tradingagents.api.serialization import extract_reports, json_safe_state


def test_extract_reports_keeps_expected_report_keys():
    state = {
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_plan": "plan",
        "trader_investment_plan": "trade",
        "final_trade_decision": "Rating: Hold",
    }
    reports = extract_reports(state)
    assert reports == state


def test_json_safe_state_drops_messages_and_stringifies_unknown_objects():
    class Unknown:
        def __str__(self):
            return "unknown-object"

    state = {"messages": [object()], "ticker": "NVDA", "value": Unknown()}
    safe = json_safe_state(state)
    assert "messages" not in safe
    assert safe["ticker"] == "NVDA"
    assert safe["value"] == "unknown-object"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/worker/test_jobs.py::test_extract_reports_keeps_expected_report_keys tests/worker/test_jobs.py::test_json_safe_state_drops_messages_and_stringifies_unknown_objects -q
```

Expected: FAIL because `tradingagents.api.serialization` does not exist.

- [ ] **Step 3: Implement serialization helpers**

Create `tradingagents/api/serialization.py`:

```python
from __future__ import annotations

import json
from typing import Any


REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)


def extract_reports(final_state: dict[str, Any]) -> dict[str, Any]:
    return {key: final_state.get(key, "") for key in REPORT_KEYS}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)


def json_safe_state(final_state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe(value)
        for key, value in final_state.items()
        if key != "messages"
    }
```

- [ ] **Step 4: Add TradingAgents execution wrapper**

Create `tradingagents/worker/__init__.py`:

```python
"""Celery worker package for TradingAgents analysis service."""
```

Create `tradingagents/worker/analysis.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any

from tradingagents.api.serialization import extract_reports, json_safe_state
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def run_tradingagents_analysis(
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    graph = TradingAgentsGraph(selected_analysts=analysts, config=config)
    final_state, decision = graph.propagate(
        ticker,
        trade_date.isoformat(),
        asset_type=asset_type,
    )
    return {
        "decision": decision,
        "reports": extract_reports(final_state),
        "final_state": json_safe_state(final_state),
    }
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/worker/test_jobs.py::test_extract_reports_keeps_expected_report_keys tests/worker/test_jobs.py::test_json_safe_state_drops_messages_and_stringifies_unknown_objects -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/serialization.py tradingagents/worker tests/worker/test_jobs.py
git commit -m "feat(worker): add analysis serialization"
```

---

## Task 6: Celery App and Worker Job

**Files:**
- Create: `tradingagents/worker/celery_app.py`
- Create: `tradingagents/worker/jobs.py`
- Modify: `tests/worker/test_jobs.py`

- [ ] **Step 1: Add failing worker success/failure tests**

Append to `tests/worker/test_jobs.py`:

```python
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.jobs import execute_analysis_run


def _repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


def test_execute_analysis_run_success_writes_result():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts):
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    assert repo.get_run(run.run_id).status == "succeeded"
    assert repo.get_result(run.run_id).decision == "Hold"


def test_execute_analysis_run_failure_writes_error():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts):
        raise RuntimeError("provider failed")

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "provider failed"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/worker/test_jobs.py::test_execute_analysis_run_success_writes_result tests/worker/test_jobs.py::test_execute_analysis_run_failure_writes_error -q
```

Expected: FAIL because `tradingagents.worker.jobs` does not exist.

- [ ] **Step 3: Implement Celery app and job**

Create `tradingagents/worker/celery_app.py`:

```python
from __future__ import annotations

from celery import Celery

from tradingagents.api.config import get_api_settings

settings = get_api_settings()

celery_app = Celery(
    "tradingagents",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=settings.task_time_limit_seconds,
)
celery_app.autodiscover_tasks(["tradingagents.worker"])
```

Create `tradingagents/worker/jobs.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tradingagents.api.db import SessionLocal
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app

AnalysisExecutor = Callable[[str, object, str, list[str]], dict[str, Any]]


def execute_analysis_run(
    repo: AnalysisRunRepository,
    run_id: str,
    executor: AnalysisExecutor = run_tradingagents_analysis,
) -> None:
    run = repo.get_run(run_id)
    if run is None or run.status != "queued":
        return

    try:
        repo.mark_running(run_id)
        repo.session.commit()
        output = executor(run.ticker, run.trade_date, run.asset_type, run.analysts)
        repo.store_success(
            run_id=run_id,
            decision=output["decision"],
            reports=output["reports"],
            final_state=output["final_state"],
        )
        repo.session.commit()
    except Exception as exc:
        repo.session.rollback()
        repo.store_failure(run_id, str(exc))
        repo.session.commit()


@celery_app.task(name="tradingagents.worker.jobs.run_analysis_task")
def run_analysis_task(run_id: str) -> None:
    with SessionLocal() as session:
        repo = AnalysisRunRepository(session)
        execute_analysis_run(repo, run_id)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/worker/test_jobs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker tests/worker/test_jobs.py
git commit -m "feat(worker): add celery analysis task"
```

---

## Task 7: FastAPI Dependencies and Run Routes

**Files:**
- Create: `tradingagents/api/deps.py`
- Create: `tradingagents/api/routers/__init__.py`
- Create: `tradingagents/api/routers/runs.py`
- Create: `tradingagents/api/app.py`
- Test: `tests/api/test_runs_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/api/test_runs_routes.py`:

```python
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base
from tradingagents.api.deps import get_db_session, get_task_enqueue
from tradingagents.api.repositories import AnalysisRunRepository


def _client():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    task_ids = []

    def override_session():
        with Session() as session:
            yield session

    def enqueue(run_id: str) -> str:
        task_ids.append(run_id)
        return "celery-test-id"

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_task_enqueue] = lambda: enqueue
    return TestClient(app), Session, task_ids


def test_post_runs_creates_run_and_enqueues_task():
    client, Session, task_ids = _client()
    response = client.post("/runs", json={
        "ticker": "nvda",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "analysts": ["market"],
    })

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_id"].startswith("run_")
    assert task_ids == [body["run_id"]]

    with Session() as session:
        run = AnalysisRunRepository(session).get_run(body["run_id"])
        assert run.ticker == "NVDA"
        assert run.celery_task_id == "celery-test-id"


def test_get_run_returns_status():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        session.commit()

    response = client.get(f"/runs/{run.run_id}")
    assert response.status_code == 200
    assert response.json()["ticker"] == "NVDA"


def test_result_before_completion_returns_409():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        session.commit()

    response = client.get(f"/runs/{run.run_id}/result")
    assert response.status_code == 409


def test_result_after_completion_returns_payload():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.mark_running(run.run_id)
        repo.store_success(run.run_id, "Hold", {"final_trade_decision": "Rating: Hold"}, {"ticker": "NVDA"})
        session.commit()

    response = client.get(f"/runs/{run.run_id}/result")
    assert response.status_code == 200
    assert response.json()["decision"] == "Hold"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/api/test_runs_routes.py -q
```

Expected: FAIL because FastAPI app and route modules do not exist.

- [ ] **Step 3: Implement dependencies**

Create `tradingagents/api/deps.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session

from tradingagents.api.db import get_session
from tradingagents.worker.jobs import run_analysis_task


def get_db_session() -> Iterator[Session]:
    yield from get_session()


def enqueue_analysis_task(run_id: str) -> str:
    result = run_analysis_task.delay(run_id)
    return result.id


def get_task_enqueue() -> Callable[[str], str]:
    return enqueue_analysis_task
```

Create `tradingagents/api/routers/__init__.py`:

```python
"""FastAPI routers for TradingAgents API."""
```

- [ ] **Step 4: Implement run routes**

Create `tradingagents/api/routers/runs.py`:

```python
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from tradingagents.api.deps import get_db_session, get_task_enqueue
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.schemas import CreateRunRequest, CreateRunResponse, RunResultResponse, RunStatusResponse

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: CreateRunRequest,
    session: Session = Depends(get_db_session),
    enqueue=Depends(get_task_enqueue),
):
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker=request.ticker,
        trade_date=request.trade_date,
        asset_type=request.asset_type,
        analysts=list(request.analysts),
    )
    session.flush()
    task_id = enqueue(run.run_id)
    repo.set_celery_task_id(run.run_id, task_id)
    session.commit()
    return CreateRunResponse(run_id=run.run_id, status="queued")


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, session: Session = Depends(get_db_session)):
    repo = AnalysisRunRepository(session)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/result", response_model=RunResultResponse)
def get_result(run_id: str, session: Session = Depends(get_db_session)):
    repo = AnalysisRunRepository(session)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status == "failed":
        raise HTTPException(status_code=409, detail=run.error or "run failed")
    if run.status != "succeeded":
        raise HTTPException(status_code=409, detail="run not completed")
    result = repo.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=409, detail="result not available")
    return RunResultResponse(
        run_id=run_id,
        status="succeeded",
        decision=result.decision,
        reports=result.reports,
        final_state=result.final_state,
        created_at=result.created_at,
    )


@router.get("/{run_id}/events")
async def stream_events(run_id: str, session: Session = Depends(get_db_session)):
    repo = AnalysisRunRepository(session)
    if repo.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def event_generator():
        last_id = 0
        terminal = False
        while not terminal:
            events = repo.list_events(run_id, after_id=last_id)
            for event in events:
                last_id = event.id
                yield f"event: {event.event_type}\\n"
                yield f"data: {json.dumps(event.payload)}\\n\\n"
                if event.event_type in {"run_succeeded", "run_failed"}:
                    terminal = True
            if not terminal:
                await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 5: Implement app factory**

Create `tradingagents/api/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from tradingagents.api.db import init_db
from tradingagents.api.routers import runs


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analysis API")
    app.include_router(runs.router)

    @app.on_event("startup")
    def _startup():
        init_db()

    return app


app = create_app()
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_runs_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/api tests/api/test_runs_routes.py
git commit -m "feat(api): add analysis run routes"
```

---

## Task 8: Health Route

**Files:**
- Create: `tradingagents/api/routers/health.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_health.py`

- [ ] **Step 1: Write failing health test**

Create `tests/api/test_health.py`:

```python
from fastapi.testclient import TestClient

from tradingagents.api.app import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/api/test_health.py -q
```

Expected: FAIL with `404 Not Found` for `/health`.

- [ ] **Step 3: Implement health route**

Create `tradingagents/api/routers/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

from tradingagents.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", postgres="ok", redis="ok")
```

Modify `tradingagents/api/app.py`:

```python
from tradingagents.api.routers import health, runs


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analysis API")
    app.include_router(health.router)
    app.include_router(runs.router)
    ...
```

- [ ] **Step 4: Run test to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_health.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/health.py tradingagents/api/app.py tests/api/test_health.py
git commit -m "feat(api): add health endpoint"
```

---

## Task 9: SSE Historical Events

**Files:**
- Modify: `tests/api/test_sse_events.py`
- Modify: `tradingagents/api/routers/runs.py` if the route needs fixes.

- [ ] **Step 1: Write failing SSE test**

Create `tests/api/test_sse_events.py`:

```python
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base
from tradingagents.api.deps import get_db_session
from tradingagents.api.repositories import AnalysisRunRepository


def test_events_stream_emits_historical_events_in_order():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.mark_running(run.run_id)
        repo.store_success(run.run_id, "Hold", {"final_trade_decision": "Rating: Hold"}, {"ticker": "NVDA"})
        session.commit()

    client = TestClient(app)
    with client.stream("GET", f"/runs/{run.run_id}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: run_queued" in text
    assert "event: run_started" in text
    assert "event: run_succeeded" in text
    assert text.index("run_queued") < text.index("run_started") < text.index("run_succeeded")
```

- [ ] **Step 2: Run test to verify RED or expose bug**

Run:

```bash
python -m pytest tests/api/test_sse_events.py -q
```

Expected before fixes: may FAIL if the route holds a closed DB session, does not terminate, or serializes payload incorrectly. If it already passes, record that SSE behavior is covered.

- [ ] **Step 3: Fix SSE route if needed**

If the dependency session closes too early for streaming, refactor `stream_events` to open a fresh session inside the generator using `SessionLocal`:

```python
from tradingagents.api.db import SessionLocal


@router.get("/{run_id}/events")
async def stream_events(run_id: str, session: Session = Depends(get_db_session)):
    if AnalysisRunRepository(session).get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def event_generator():
        last_id = 0
        terminal = False
        while not terminal:
            with SessionLocal() as stream_session:
                repo = AnalysisRunRepository(stream_session)
                events = repo.list_events(run_id, after_id=last_id)
                for event in events:
                    last_id = event.id
                    yield f"event: {event.event_type}\\n"
                    yield f"data: {json.dumps(event.payload)}\\n\\n"
                    if event.event_type in {"run_succeeded", "run_failed"}:
                        terminal = True
            if not terminal:
                await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

If this refactor breaks dependency override tests, keep the dependency-session version and document that first-version SSE tests use historical terminal events only.

- [ ] **Step 4: Run test to verify GREEN**

Run:

```bash
python -m pytest tests/api/test_sse_events.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/runs.py tests/api/test_sse_events.py
git commit -m "test(api): cover analysis run events stream"
```

---

## Task 10: End-to-End Verification and Documentation Touch-Up

**Files:**
- Modify: `docs/superpowers/specs/2026-05-26-analysis-http-api-design.md` only if implementation details diverged.
- Optional modify: `README.md` or `RUNNING.md` if the user wants public run instructions in top-level docs.

- [ ] **Step 1: Run focused API/worker tests**

Run:

```bash
python -m pytest tests/api tests/worker -q
```

Expected: PASS.

- [ ] **Step 2: Run existing unit tests**

Run:

```bash
python -m pytest tests -q
```

Expected: PASS. If external-service tests fail because of missing credentials, verify the failure is not caused by the new API/worker changes and record the exact failing tests.

- [ ] **Step 3: Compile source**

Run:

```bash
python -m compileall -q tradingagents tradingbot cli tests
```

Expected: PASS.

- [ ] **Step 4: Smoke import API and worker modules**

Run:

```bash
python - <<'PY'
from tradingagents.api.app import app
from tradingagents.worker.celery_app import celery_app
print(app.title)
print(celery_app.main)
PY
```

Expected output contains:

```text
TradingAgents Analysis API
tradingagents
```

- [ ] **Step 5: Commit final verification/doc updates**

If documentation changed:

```bash
git add docs README.md RUNNING.md
git commit -m "docs: document analysis api deployment"
```

If no docs changed, skip this commit.

---

## Execution Notes

- Do not call real LLM providers in tests.
- Do not add trading, broker, portfolio, approval, or auth endpoints in this implementation.
- Keep API request config limited to `ticker`, `trade_date`, `asset_type`, and `analysts`.
- Keep Celery retry disabled by default.
- Keep worker concurrency guidance conservative: first deployment should use `--concurrency=1`.
- Preserve existing user changes in unrelated files, especially current `uv.lock`, `.DS_Store`, `docs/integration-api-rpc.md`, and `docs/project-deep-dive.md` worktree state unless the implementation task explicitly touches them.

