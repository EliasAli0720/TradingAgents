# Stock Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a database-backed stock recommendation workspace where users maintain a watchlist, generate 5 model-backed recommendations, review recommendation history, and manually create analysis runs for selected recommendations.

**Architecture:** Store watchlists, recommendation batches, and recommendation items in new additive SQLAlchemy tables. Add a small recommendation service that uses the current user's analysis model quick LLM, then expose FastAPI routes consumed by a new React `/recommendations` page. Analysis creation reuses the existing run repository, model settings snapshot, capacity checks, and default stock/full-analyst parameters.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, LangChain-compatible LLM client factory, React, React Query, React Router, TypeScript, Vite.

---

## File Structure

- Modify `tradingagents/api/models.py`: add `UserWatchlist`, `RecommendationBatch`, and `RecommendationItem`.
- Modify `tradingagents/api/schemas.py`: add request/response schemas for watchlists, batches, recommendation items, generation, and analysis creation.
- Create `tradingagents/api/recommendation_repository.py`: persistence and user-scoped queries for watchlists, batches, and items.
- Create `tradingagents/api/recommendation_service.py`: prompt construction, LLM invocation, output parsing, ticker validation, and recent-analysis context selection.
- Create `tradingagents/api/routers/recommendations.py`: authenticated recommendation routes.
- Modify `tradingagents/api/app.py`: include the recommendations router.
- Modify `web/src/api/recommendations.ts`: typed API client.
- Modify `web/src/router.tsx`: add `/recommendations`.
- Modify `web/src/components/layout/Sidebar.tsx`: replace the full-page refresh button with navigation to recommendations.
- Modify `web/src/i18n.ts`: add recommendation labels and remove unused refresh labels referenced by `Sidebar`.
- Create `web/src/routes/recommendations/index.tsx`: recommendation workspace.
- Add tests:
  - `tests/api/test_recommendation_repository.py`
  - `tests/api/test_recommendation_service.py`
  - `tests/api/test_recommendation_routes.py`

## Task 1: Recommendation Persistence

**Files:**
- Modify: `tradingagents/api/models.py`
- Create: `tradingagents/api/recommendation_repository.py`
- Test: `tests/api/test_recommendation_repository.py`

- [ ] **Step 1: Write repository tests for watchlist normalization and persistence**

Create `tests/api/test_recommendation_repository.py`:

```python
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import User
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.repositories import utcnow


def _session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _user(session, user_id="u1", username="alice"):
    user = User(
        user_id=user_id,
        username=username,
        password_hash="hash",
        role="operator",
        is_active=True,
        language="zh",
        created_at=utcnow(),
    )
    session.add(user)
    session.commit()
    return user


def test_watchlist_upsert_normalizes_and_deduplicates():
    with _session() as session:
        user = _user(session)
        repo = RecommendationRepository(session)

        row = repo.upsert_watchlist(user.user_id, [" nvda ", "AAPL", "nvda", "msft"])
        session.commit()

        assert row.tickers == ["NVDA", "AAPL", "MSFT"]
        assert repo.get_watchlist(user.user_id).tickers == ["NVDA", "AAPL", "MSFT"]


def test_watchlist_rejects_empty_and_invalid_tickers():
    with _session() as session:
        user = _user(session)
        repo = RecommendationRepository(session)

        try:
            repo.upsert_watchlist(user.user_id, [])
        except ValueError as exc:
            assert "at least one ticker" in str(exc)
        else:
            raise AssertionError("empty watchlist accepted")

        try:
            repo.upsert_watchlist(user.user_id, ["AAPL", "../BAD"])
        except ValueError as exc:
            assert "invalid ticker" in str(exc)
        else:
            raise AssertionError("invalid ticker accepted")
```

- [ ] **Step 2: Run the repository tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_repository.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'tradingagents.api.recommendation_repository'`.

- [ ] **Step 3: Add SQLAlchemy models**

In `tradingagents/api/models.py`, add imports if missing:

```python
from sqlalchemy import ForeignKey
```

Then add these model classes after `AnalysisMemoryEntry`:

```python
class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    tickers: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationBatch(Base):
    __tablename__ = "recommendation_batches"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    watchlist_snapshot: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_recommendation_batches_user_created", "user_id", "created_at"),)


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("recommendation_batches.batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_recommendation_items_user_status", "user_id", "status"),
        Index("idx_recommendation_items_batch_priority", "batch_id", "priority"),
    )
```

- [ ] **Step 4: Add repository implementation**

Create `tradingagents/api/recommendation_repository.py`:

```python
from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.models import (
    AnalysisRun,
    AnalysisRunResult,
    RecommendationBatch,
    RecommendationItem,
    UserWatchlist,
)
from tradingagents.api.repositories import utcnow


_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")


def _new_batch_id() -> str:
    return f"rec_{uuid4().hex}"


def _new_item_id() -> str:
    return f"reci_{uuid4().hex}"


def normalize_tickers(tickers: list[str], *, max_count: int = 50) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        if not _TICKER_RE.match(ticker):
            raise ValueError(f"invalid ticker: {raw}")
        if ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    if not out:
        raise ValueError("at least one ticker is required")
    if len(out) > max_count:
        raise ValueError(f"watchlist cannot exceed {max_count} tickers")
    return out


class RecommendationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_watchlist(self, user_id: str) -> UserWatchlist | None:
        return self.session.get(UserWatchlist, user_id)

    def upsert_watchlist(self, user_id: str, tickers: list[str]) -> UserWatchlist:
        normalized = normalize_tickers(tickers)
        now = utcnow()
        row = self.get_watchlist(user_id)
        if row is None:
            row = UserWatchlist(
                user_id=user_id,
                tickers=normalized,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            return row
        row.tickers = normalized
        row.updated_at = now
        return row

    def create_batch(
        self,
        user_id: str,
        watchlist_snapshot: list[str],
        model_snapshot: dict[str, Any],
        items: list[dict[str, Any]],
        *,
        prompt_version: str = "stock-recommendations-v1",
    ) -> RecommendationBatch:
        now = utcnow()
        batch = RecommendationBatch(
            batch_id=_new_batch_id(),
            user_id=user_id,
            status="succeeded",
            watchlist_snapshot=list(watchlist_snapshot),
            model_snapshot=model_snapshot,
            prompt_version=prompt_version,
            error=None,
            created_at=now,
        )
        self.session.add(batch)
        for index, item in enumerate(items, start=1):
            self.session.add(
                RecommendationItem(
                    item_id=_new_item_id(),
                    batch_id=batch.batch_id,
                    user_id=user_id,
                    ticker=item["ticker"],
                    source=item["source"],
                    priority=int(item.get("priority") or index),
                    reason=item["reason"],
                    risk=item["risk"],
                    status="recommended",
                    run_id=None,
                    error=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return batch

    def get_batch(self, user_id: str, batch_id: str) -> RecommendationBatch | None:
        stmt = select(RecommendationBatch).where(
            RecommendationBatch.user_id == user_id,
            RecommendationBatch.batch_id == batch_id,
        )
        return self.session.scalar(stmt)

    def list_batches(self, user_id: str, limit: int = 20) -> list[RecommendationBatch]:
        stmt = (
            select(RecommendationBatch)
            .where(RecommendationBatch.user_id == user_id)
            .order_by(RecommendationBatch.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_items(self, user_id: str, batch_id: str) -> list[RecommendationItem]:
        stmt = (
            select(RecommendationItem)
            .where(
                RecommendationItem.user_id == user_id,
                RecommendationItem.batch_id == batch_id,
            )
            .order_by(RecommendationItem.priority.asc(), RecommendationItem.created_at.asc())
        )
        return list(self.session.scalars(stmt))

    def recent_analysis_context(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        stmt = (
            select(AnalysisRun, AnalysisRunResult)
            .join(AnalysisRunResult, AnalysisRunResult.run_id == AnalysisRun.run_id)
            .where(AnalysisRun.user_id == user_id, AnalysisRun.status == "succeeded")
            .order_by(AnalysisRun.finished_at.desc().nullslast(), AnalysisRun.created_at.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return [
            {
                "ticker": run.ticker,
                "trade_date": run.trade_date.isoformat(),
                "decision": result.decision,
                "final_trade_decision": str(result.reports.get("final_trade_decision", ""))[:600],
            }
            for run, result in rows
        ]
```

- [ ] **Step 5: Run repository tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_repository.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit persistence layer**

```bash
git add tradingagents/api/models.py tradingagents/api/recommendation_repository.py tests/api/test_recommendation_repository.py
git commit -m "feat(api): add recommendation persistence"
```

## Task 2: Watchlist API

**Files:**
- Modify: `tradingagents/api/schemas.py`
- Create: `tradingagents/api/routers/recommendations.py`
- Modify: `tradingagents/api/app.py`
- Test: `tests/api/test_recommendation_routes.py`

- [ ] **Step 1: Write route tests for watchlist GET/PUT**

Create `tests/api/test_recommendation_routes.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session


def _client():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    return client


def _login(client: TestClient, username="alice", password="hunter22a") -> str:
    client.post("/auth/register", json={"username": username, "password": password})
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    csrf = client.cookies.get("tradingagents_csrf")
    client.headers.update({"X-CSRF-Token": csrf})
    return csrf


def test_watchlist_requires_authentication():
    client = _client()

    response = client.get("/recommendations/watchlist")

    assert response.status_code == 401


def test_watchlist_get_put_roundtrip():
    client = _client()
    _login(client)

    empty = client.get("/recommendations/watchlist")
    assert empty.status_code == 200
    assert empty.json()["tickers"] == []
    assert empty.json()["updated_at"] is None

    saved = client.put(
        "/recommendations/watchlist",
        json={"tickers": [" nvda ", "AAPL", "nvda"]},
    )
    assert saved.status_code == 200
    assert saved.json()["tickers"] == ["NVDA", "AAPL"]
    assert saved.json()["updated_at"] is not None

    loaded = client.get("/recommendations/watchlist")
    assert loaded.status_code == 200
    assert loaded.json()["tickers"] == ["NVDA", "AAPL"]


def test_watchlist_rejects_invalid_ticker():
    client = _client()
    _login(client)

    response = client.put(
        "/recommendations/watchlist",
        json={"tickers": ["AAPL", "../BAD"]},
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run watchlist route tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py -q
```

Expected: fail with `404 Not Found` for `/recommendations/watchlist`.

- [ ] **Step 3: Add recommendation schemas**

In `tradingagents/api/schemas.py`, add:

```python
class WatchlistRequest(BaseModel):
    tickers: list[str]


class WatchlistResponse(BaseModel):
    tickers: list[str]
    updated_at: Optional[datetime] = None


class RecommendationItemResponse(BaseModel):
    item_id: str
    ticker: str
    source: Literal["watchlist", "model_expansion"]
    priority: int
    reason: str
    risk: str
    status: Literal["recommended", "analysis_queued", "analysis_failed", "ignored"]
    run_id: Optional[str] = None
    error: Optional[str] = None


class RecommendationBatchResponse(BaseModel):
    batch_id: str
    status: Literal["succeeded", "failed"]
    created_at: datetime
    items: list[RecommendationItemResponse]


class RecommendationBatchSummaryResponse(BaseModel):
    batch_id: str
    status: Literal["succeeded", "failed"]
    created_at: datetime
    item_count: int
```

- [ ] **Step 4: Add recommendations router with watchlist endpoints**

Create `tradingagents/api/routers/recommendations.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.models import User
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.schemas import WatchlistRequest, WatchlistResponse


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    row = RecommendationRepository(session).get_watchlist(user.user_id)
    if row is None:
        return WatchlistResponse(tickers=[], updated_at=None)
    return WatchlistResponse(tickers=row.tickers, updated_at=row.updated_at)


@router.put("/watchlist", response_model=WatchlistResponse)
def put_watchlist(
    request: WatchlistRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    repo = RecommendationRepository(session)
    try:
        row = repo.upsert_watchlist(user.user_id, request.tickers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return WatchlistResponse(tickers=row.tickers, updated_at=row.updated_at)
```

- [ ] **Step 5: Include router in app**

Modify `tradingagents/api/app.py` imports:

```python
from tradingagents.api.routers import (
    admin,
    auth,
    broker,
    capacity,
    health,
    recommendations,
    runs,
    settings,
)
```

Then include it:

```python
app.include_router(recommendations.router)
```

- [ ] **Step 6: Run watchlist route tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py::test_watchlist_requires_authentication tests/api/test_recommendation_routes.py::test_watchlist_get_put_roundtrip tests/api/test_recommendation_routes.py::test_watchlist_rejects_invalid_ticker -q
```

Expected: `3 passed`.

- [ ] **Step 7: Commit watchlist API**

```bash
git add tradingagents/api/schemas.py tradingagents/api/routers/recommendations.py tradingagents/api/app.py tests/api/test_recommendation_routes.py
git commit -m "feat(api): add recommendation watchlist routes"
```

## Task 3: Recommendation Service

**Files:**
- Create: `tradingagents/api/recommendation_service.py`
- Modify: `tradingagents/api/recommendation_repository.py`
- Test: `tests/api/test_recommendation_service.py`

- [ ] **Step 1: Write service tests for output parsing and context**

Create `tests/api/test_recommendation_service.py`:

```python
from datetime import date

from tradingagents.api.recommendation_service import (
    RecommendationCandidate,
    RecommendationGenerator,
    parse_recommendations,
)


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return type("Msg", (), {"content": self.content})()


def test_parse_recommendations_deduplicates_and_rejects_invalid():
    raw = """
    {
      "recommendations": [
        {"ticker":"nvda","source":"watchlist","priority":1,"reason":"AI demand","risk":"Valuation"},
        {"ticker":"../BAD","source":"model_expansion","priority":2,"reason":"bad","risk":"bad"},
        {"ticker":"NVDA","source":"watchlist","priority":3,"reason":"duplicate","risk":"duplicate"},
        {"ticker":"MSFT","source":"model_expansion","priority":4,"reason":"Cloud","risk":"FX"}
      ]
    }
    """

    parsed = parse_recommendations(raw)

    assert [item.ticker for item in parsed] == ["NVDA", "MSFT"]
    assert parsed[0].source == "watchlist"
    assert parsed[1].source == "model_expansion"


def test_generator_invokes_llm_with_watchlist_and_recent_context():
    llm = FakeLLM(
        '{"recommendations":[{"ticker":"NVDA","source":"watchlist","priority":1,'
        '"reason":"AI infrastructure leader","risk":"Valuation compression"}]}'
    )
    generator = RecommendationGenerator(llm=llm)

    items = generator.generate(
        watchlist=["NVDA", "AAPL"],
        recent_context=[{"ticker": "AAPL", "decision": "Hold", "final_trade_decision": "Rating: Hold"}],
        today=date(2026, 5, 31),
    )

    assert items == [
        RecommendationCandidate(
            ticker="NVDA",
            source="watchlist",
            priority=1,
            reason="AI infrastructure leader",
            risk="Valuation compression",
        )
    ]
    prompt_text = str(llm.messages)
    assert "NVDA" in prompt_text
    assert "AAPL" in prompt_text
    assert "2026-05-31" in prompt_text
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_service.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'tradingagents.api.recommendation_service'`.

- [ ] **Step 3: Implement recommendation parsing and generator**

Create `tradingagents/api/recommendation_service.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")
PROMPT_VERSION = "stock-recommendations-v1"


class _LLMRecommendation(BaseModel):
    ticker: str
    source: Literal["watchlist", "model_expansion"]
    priority: int = Field(ge=1)
    reason: str
    risk: str


class _LLMRecommendationPayload(BaseModel):
    recommendations: list[_LLMRecommendation]


@dataclass(frozen=True)
class RecommendationCandidate:
    ticker: str
    source: Literal["watchlist", "model_expansion"]
    priority: int
    reason: str
    risk: str


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "\\n".join(str(part) for part in content)
    return str(content)


def parse_recommendations(raw: str) -> list[RecommendationCandidate]:
    try:
        payload = _LLMRecommendationPayload.model_validate_json(raw)
    except ValidationError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            payload = _LLMRecommendationPayload.model_validate(json.loads(raw[start : end + 1]))
        except (ValidationError, json.JSONDecodeError):
            return []

    out: list[RecommendationCandidate] = []
    seen: set[str] = set()
    for item in payload.recommendations:
        ticker = item.ticker.strip().upper()
        if not _TICKER_RE.match(ticker):
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(
            RecommendationCandidate(
                ticker=ticker,
                source=item.source,
                priority=item.priority,
                reason=item.reason.strip(),
                risk=item.risk.strip(),
            )
        )
    return out


class RecommendationGenerator:
    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        *,
        watchlist: list[str],
        recent_context: list[dict[str, Any]],
        today: date,
    ) -> list[RecommendationCandidate]:
        system = (
            "You recommend stocks for pre-analysis triage. "
            "Return only valid JSON with a recommendations array. "
            "Recommend exactly 5 stock tickers when possible. "
            "Prefer the watchlist, but use source=model_expansion for justified additions. "
            "Do not claim that analysis has already been performed."
        )
        user = {
            "date": today.isoformat(),
            "watchlist": watchlist,
            "recent_analysis_context": recent_context,
            "schema": {
                "recommendations": [
                    {
                        "ticker": "AAPL",
                        "source": "watchlist",
                        "priority": 1,
                        "reason": "Concise recommendation reason",
                        "risk": "Concise risk note",
                    }
                ]
            },
        }
        response = self.llm.invoke(
            [
                ("system", system),
                ("human", json.dumps(user, ensure_ascii=False)),
            ]
        )
        return parse_recommendations(_message_content(response))
```

- [ ] **Step 4: Run service tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_service.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit service**

```bash
git add tradingagents/api/recommendation_service.py tests/api/test_recommendation_service.py
git commit -m "feat(api): add recommendation generation service"
```

## Task 4: Generate and Read Recommendation Batches

**Files:**
- Modify: `tradingagents/api/routers/recommendations.py`
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/recommendation_repository.py`
- Test: `tests/api/test_recommendation_routes.py`

- [ ] **Step 1: Add route tests for generate/list/detail**

Append to `tests/api/test_recommendation_routes.py`:

```python
from tradingagents.api.recommendation_service import RecommendationCandidate


class FakeGenerator:
    def generate(self, *, watchlist, recent_context, today):
        assert watchlist == ["NVDA", "AAPL"]
        return [
            RecommendationCandidate(
                ticker="NVDA",
                source="watchlist",
                priority=1,
                reason="AI infrastructure leader",
                risk="Valuation sensitivity",
            ),
            RecommendationCandidate(
                ticker="MSFT",
                source="model_expansion",
                priority=2,
                reason="Cloud and enterprise AI exposure",
                risk="Large-cap multiple risk",
            ),
        ]


def _put_model_settings(client: TestClient):
    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
        },
    )
    assert response.status_code == 200


def test_generate_requires_model_settings():
    client = _client()
    _login(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    response = client.post("/recommendations/generate", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "model settings not configured"


def test_generate_requires_watchlist():
    client = _client()
    _login(client)
    _put_model_settings(client)

    response = client.post("/recommendations/generate", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "watchlist not configured"


def test_generate_saves_batch_and_history(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(recommendations, "build_recommendation_generator", lambda settings: FakeGenerator())

    response = client.post("/recommendations/generate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"].startswith("rec_")
    assert [item["ticker"] for item in body["items"]] == ["NVDA", "MSFT"]
    assert body["items"][1]["source"] == "model_expansion"

    batches = client.get("/recommendations/batches")
    assert batches.status_code == 200
    assert batches.json()[0]["batch_id"] == body["batch_id"]
    assert batches.json()[0]["item_count"] == 2

    detail = client.get(f"/recommendations/batches/{body['batch_id']}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["reason"] == "AI infrastructure leader"
```

- [ ] **Step 2: Run route tests and verify new tests fail**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py -q
```

Expected: fail with `404 Not Found` for generate/list/detail routes or missing helper functions.

- [ ] **Step 3: Add generate request schema and response helpers**

In `tradingagents/api/schemas.py`, add:

```python
class GenerateRecommendationsRequest(BaseModel):
    pass
```

In `tradingagents/api/routers/recommendations.py`, add imports:

```python
from datetime import date

from tradingagents.api.crypto import decrypt_secret
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.recommendation_service import RecommendationGenerator
from tradingagents.llm_clients import create_llm_client
from tradingagents.api.schemas import (
    GenerateRecommendationsRequest,
    RecommendationBatchResponse,
    RecommendationBatchSummaryResponse,
    RecommendationItemResponse,
)
```

Add helpers:

```python
def _item_response(item) -> RecommendationItemResponse:
    return RecommendationItemResponse(
        item_id=item.item_id,
        ticker=item.ticker,
        source=item.source,
        priority=item.priority,
        reason=item.reason,
        risk=item.risk,
        status=item.status,
        run_id=item.run_id,
        error=item.error,
    )


def _batch_response(repo: RecommendationRepository, user_id: str, batch) -> RecommendationBatchResponse:
    return RecommendationBatchResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        created_at=batch.created_at,
        items=[_item_response(item) for item in repo.list_items(user_id, batch.batch_id)],
    )


def build_recommendation_generator(settings) -> RecommendationGenerator:
    kwargs = {}
    if settings.encrypted_api_key:
        kwargs["api_key"] = decrypt_secret(settings.encrypted_api_key)
    client = create_llm_client(
        provider=settings.llm_provider,
        model=settings.quick_think_llm,
        base_url=settings.backend_url,
        **kwargs,
    )
    return RecommendationGenerator(client.get_llm())
```

- [ ] **Step 4: Add generate/list/detail routes**

Append to `tradingagents/api/routers/recommendations.py`:

```python
@router.post("/generate", response_model=RecommendationBatchResponse)
def generate_recommendations(
    _request: GenerateRecommendationsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    settings = UserModelSettingsRepository(session).get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=409, detail="model settings not configured")
    repo = RecommendationRepository(session)
    watchlist = repo.get_watchlist(user.user_id)
    if watchlist is None or not watchlist.tickers:
        raise HTTPException(status_code=409, detail="watchlist not configured")

    generator = build_recommendation_generator(settings)
    candidates = generator.generate(
        watchlist=watchlist.tickers,
        recent_context=repo.recent_analysis_context(user.user_id),
        today=date.today(),
    )
    if not candidates:
        raise HTTPException(status_code=502, detail="model returned no valid recommendations")

    model_snapshot = {
        "llm_provider": settings.llm_provider,
        "quick_think_llm": settings.quick_think_llm,
        "deep_think_llm": settings.deep_think_llm,
        "backend_url": settings.backend_url,
    }
    batch = repo.create_batch(
        user_id=user.user_id,
        watchlist_snapshot=watchlist.tickers,
        model_snapshot=model_snapshot,
        items=[candidate.__dict__ for candidate in candidates[:5]],
    )
    session.commit()
    return _batch_response(repo, user.user_id, batch)


@router.get("/batches", response_model=list[RecommendationBatchSummaryResponse])
def list_batches(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    repo = RecommendationRepository(session)
    response = []
    for batch in repo.list_batches(user.user_id):
        response.append(
            RecommendationBatchSummaryResponse(
                batch_id=batch.batch_id,
                status=batch.status,
                created_at=batch.created_at,
                item_count=len(repo.list_items(user.user_id, batch.batch_id)),
            )
        )
    return response


@router.get("/batches/{batch_id}", response_model=RecommendationBatchResponse)
def get_batch(
    batch_id: str,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    repo = RecommendationRepository(session)
    batch = repo.get_batch(user.user_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="recommendation batch not found")
    return _batch_response(repo, user.user_id, batch)
```

- [ ] **Step 5: Run generate/list/detail tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py -q
```

Expected: all route tests pass.

- [ ] **Step 6: Commit generation routes**

```bash
git add tradingagents/api/schemas.py tradingagents/api/routers/recommendations.py tradingagents/api/recommendation_repository.py tests/api/test_recommendation_routes.py
git commit -m "feat(api): add recommendation generation routes"
```

## Task 5: Analyze Selected Recommendations

**Files:**
- Modify: `tradingagents/api/recommendation_repository.py`
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/routers/recommendations.py`
- Test: `tests/api/test_recommendation_routes.py`

- [ ] **Step 1: Add route test for creating analysis runs from selected items**

Append to `tests/api/test_recommendation_routes.py`:

```python
def test_analyze_selected_items_creates_default_stock_runs(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(recommendations, "build_recommendation_generator", lambda settings: FakeGenerator())
    batch = client.post("/recommendations/generate", json={}).json()
    item_id = batch["items"][0]["item_id"]

    response = client.post(
        f"/recommendations/batches/{batch['batch_id']}/analyze",
        json={"item_ids": [item_id]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == []
    assert body["created"][0]["item_id"] == item_id
    assert body["created"][0]["ticker"] == "NVDA"
    assert body["created"][0]["run_id"].startswith("run_")

    refreshed = client.get(f"/recommendations/batches/{batch['batch_id']}").json()
    item = refreshed["items"][0]
    assert item["status"] == "analysis_queued"
    assert item["run_id"] == body["created"][0]["run_id"]

    run = client.get(f"/runs/{item['run_id']}").json()
    assert run["ticker"] == "NVDA"
    assert run["asset_type"] == "stock"
    assert run["analysts"] == ["market", "social", "news", "fundamentals"]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py::test_analyze_selected_items_creates_default_stock_runs -q
```

Expected: fail with `404 Not Found` for `/analyze`.

- [ ] **Step 3: Add analyze schemas**

In `tradingagents/api/schemas.py`, add:

```python
class AnalyzeRecommendationsRequest(BaseModel):
    item_ids: list[str]


class AnalyzeRecommendationCreatedResponse(BaseModel):
    item_id: str
    ticker: str
    run_id: str


class AnalyzeRecommendationFailedResponse(BaseModel):
    item_id: str
    ticker: Optional[str] = None
    detail: str


class AnalyzeRecommendationsResponse(BaseModel):
    created: list[AnalyzeRecommendationCreatedResponse]
    failed: list[AnalyzeRecommendationFailedResponse]
```

- [ ] **Step 4: Add repository method for marking item run linkage**

In `tradingagents/api/recommendation_repository.py`, add:

```python
    def get_items_by_ids(
        self,
        user_id: str,
        batch_id: str,
        item_ids: list[str],
    ) -> list[RecommendationItem]:
        if not item_ids:
            return []
        stmt = select(RecommendationItem).where(
            RecommendationItem.user_id == user_id,
            RecommendationItem.batch_id == batch_id,
            RecommendationItem.item_id.in_(item_ids),
        )
        return list(self.session.scalars(stmt))

    def mark_analysis_queued(self, item: RecommendationItem, run_id: str) -> None:
        item.status = "analysis_queued"
        item.run_id = run_id
        item.error = None
        item.updated_at = utcnow()

    def mark_analysis_failed(self, item: RecommendationItem, detail: str) -> None:
        item.status = "recommended"
        item.error = detail
        item.updated_at = utcnow()
```

- [ ] **Step 5: Add analyze route**

In `tradingagents/api/routers/recommendations.py`, add imports:

```python
from tradingagents.api.capacity import CapacityConfig, capacity_snapshot
from tradingagents.api.config import get_api_settings
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.schemas import (
    AnalyzeRecommendationCreatedResponse,
    AnalyzeRecommendationFailedResponse,
    AnalyzeRecommendationsRequest,
    AnalyzeRecommendationsResponse,
)
```

Append route:

```python
@router.post("/batches/{batch_id}/analyze", response_model=AnalyzeRecommendationsResponse)
def analyze_recommendations(
    batch_id: str,
    request: AnalyzeRecommendationsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    if user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="role required")
    settings = UserModelSettingsRepository(session).snapshot(user.user_id)
    if settings is None:
        raise HTTPException(status_code=409, detail="model settings not configured")

    repo = RecommendationRepository(session)
    batch = repo.get_batch(user.user_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="recommendation batch not found")

    items = {item.item_id: item for item in repo.get_items_by_ids(user.user_id, batch_id, request.item_ids)}
    run_repo = AnalysisRunRepository(session, user_id=user.user_id)
    api_settings = get_api_settings()
    created: list[AnalyzeRecommendationCreatedResponse] = []
    failed: list[AnalyzeRecommendationFailedResponse] = []

    for item_id in request.item_ids:
        item = items.get(item_id)
        if item is None:
            failed.append(AnalyzeRecommendationFailedResponse(item_id=item_id, detail="recommendation item not found"))
            continue
        if item.status != "recommended" or item.run_id:
            failed.append(
                AnalyzeRecommendationFailedResponse(
                    item_id=item.item_id,
                    ticker=item.ticker,
                    detail="already analyzed",
                )
            )
            continue

        capacity = capacity_snapshot(
            session,
            user.user_id,
            CapacityConfig(
                system_running=api_settings.max_running_system,
                user_running=api_settings.max_running_per_user,
                user_backlog=api_settings.max_queued_per_user,
            ),
        )
        if not capacity.can_create:
            detail = "too many queued analysis runs"
            repo.mark_analysis_failed(item, detail)
            failed.append(
                AnalyzeRecommendationFailedResponse(
                    item_id=item.item_id,
                    ticker=item.ticker,
                    detail=detail,
                )
            )
            continue

        run = run_repo.create_run(
            ticker=item.ticker,
            trade_date=date.today(),
            asset_type="stock",
            analysts=["market", "social", "news", "fundamentals"],
            user_id=user.user_id,
            llm_config=settings,
        )
        repo.mark_analysis_queued(item, run.run_id)
        created.append(
            AnalyzeRecommendationCreatedResponse(
                item_id=item.item_id,
                ticker=item.ticker,
                run_id=run.run_id,
            )
        )

    session.commit()
    return AnalyzeRecommendationsResponse(created=created, failed=failed)
```

- [ ] **Step 6: Run analyze route test and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_routes.py::test_analyze_selected_items_creates_default_stock_runs -q
```

Expected: `1 passed`.

- [ ] **Step 7: Run all recommendation API tests**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_repository.py tests/api/test_recommendation_service.py tests/api/test_recommendation_routes.py -q
```

Expected: all recommendation tests pass.

- [ ] **Step 8: Commit analyze route**

```bash
git add tradingagents/api/recommendation_repository.py tradingagents/api/schemas.py tradingagents/api/routers/recommendations.py tests/api/test_recommendation_routes.py
git commit -m "feat(api): create analysis runs from recommendations"
```

## Task 6: Frontend API, Route, Sidebar, and i18n

**Files:**
- Create: `web/src/api/recommendations.ts`
- Modify: `web/src/router.tsx`
- Modify: `web/src/components/layout/Sidebar.tsx`
- Modify: `web/src/i18n.ts`

- [ ] **Step 1: Add TypeScript recommendation API client**

Create `web/src/api/recommendations.ts`:

```ts
import { http } from './client';

export type RecommendationItem = {
  item_id: string;
  ticker: string;
  source: 'watchlist' | 'model_expansion';
  priority: number;
  reason: string;
  risk: string;
  status: 'recommended' | 'analysis_queued' | 'analysis_failed' | 'ignored';
  run_id: string | null;
  error: string | null;
};

export type RecommendationBatch = {
  batch_id: string;
  status: 'succeeded' | 'failed';
  created_at: string;
  items: RecommendationItem[];
};

export type RecommendationBatchSummary = {
  batch_id: string;
  status: 'succeeded' | 'failed';
  created_at: string;
  item_count: number;
};

export type Watchlist = {
  tickers: string[];
  updated_at: string | null;
};

export type AnalyzeRecommendationsResponse = {
  created: { item_id: string; ticker: string; run_id: string }[];
  failed: { item_id: string; ticker?: string | null; detail: string }[];
};

export const recommendationsApi = {
  async watchlist(): Promise<Watchlist> {
    const { data } = await http.get<Watchlist>('/recommendations/watchlist');
    return data;
  },
  async saveWatchlist(tickers: string[]): Promise<Watchlist> {
    const { data } = await http.put<Watchlist>('/recommendations/watchlist', { tickers });
    return data;
  },
  async generate(): Promise<RecommendationBatch> {
    const { data } = await http.post<RecommendationBatch>('/recommendations/generate', {});
    return data;
  },
  async batches(): Promise<RecommendationBatchSummary[]> {
    const { data } = await http.get<RecommendationBatchSummary[]>('/recommendations/batches');
    return data;
  },
  async batch(batchId: string): Promise<RecommendationBatch> {
    const { data } = await http.get<RecommendationBatch>(`/recommendations/batches/${batchId}`);
    return data;
  },
  async analyze(batchId: string, itemIds: string[]): Promise<AnalyzeRecommendationsResponse> {
    const { data } = await http.post<AnalyzeRecommendationsResponse>(
      `/recommendations/batches/${batchId}/analyze`,
      { item_ids: itemIds },
    );
    return data;
  },
};
```

- [ ] **Step 2: Add initial route page**

Create `web/src/routes/recommendations/index.tsx`:

```tsx
import { Subheader, Caption } from '@/components/ui/Page';
import { t } from '@/i18n';

export default function RecommendationsPage() {
  return (
    <div>
      <Subheader>{t('recommendations.title')}</Subheader>
      <Caption>{t('recommendations.caption')}</Caption>
    </div>
  );
}
```

Modify `web/src/router.tsx`:

```tsx
import RecommendationsPage from './routes/recommendations';
```

Add route under authenticated children:

```tsx
{ path: '/recommendations', element: <RecommendationsPage /> },
```

- [ ] **Step 3: Replace sidebar refresh button with navigation**

Modify `web/src/components/layout/Sidebar.tsx`:

- Remove `useState` import if it is only used for `refreshAt`.
- Remove `refreshAt` state.
- Remove the "Last refresh" block.
- Add `{ to: '/recommendations', label: 'nav.recommendations' }` to the Analysis group.
- Delete the button that calls `location.reload()`.

The Analysis group should read:

```ts
{
  title: 'group.analysis',
  items: [
    { to: '/recommendations', label: 'nav.recommendations' },
    { to: '/analysis', label: 'nav.analysis' },
    { to: '/analysis/new', label: 'nav.analysis_new' },
  ],
},
```

- [ ] **Step 4: Add i18n keys**

Modify `web/src/i18n.ts` by adding keys:

```ts
'nav.recommendations': { zh: '推荐股票', en: 'Recommendations' },
'recommendations.title': { zh: '推荐股票', en: 'Stock Recommendations' },
'recommendations.caption': { zh: '维护你的股票池，使用分析模型生成 5 支候选股票，再手动选择进入分析。', en: 'Maintain your watchlist, generate 5 model-backed candidates, then manually select stocks for analysis.' },
'recommendations.watchlist': { zh: '股票池', en: 'Watchlist' },
'recommendations.save_watchlist': { zh: '保存股票池', en: 'Save Watchlist' },
'recommendations.generate': { zh: '生成推荐', en: 'Generate Recommendations' },
'recommendations.generating': { zh: '生成中…', en: 'Generating…' },
'recommendations.start_analysis': { zh: '分析所选股票', en: 'Analyze Selected' },
'recommendations.history': { zh: '推荐历史', en: 'Recommendation History' },
'recommendations.source.watchlist': { zh: '股票池', en: 'Watchlist' },
'recommendations.source.model_expansion': { zh: '模型扩展', en: 'Model Expansion' },
'recommendations.reason': { zh: '推荐理由', en: 'Reason' },
'recommendations.risk': { zh: '风险', en: 'Risk' },
'recommendations.priority': { zh: '优先级', en: 'Priority' },
```

- [ ] **Step 5: Run frontend typecheck**

Run:

```bash
pnpm typecheck
```

from `web/`.

Expected: `tsc --noEmit` exits 0.

- [ ] **Step 6: Commit frontend shell**

```bash
git add web/src/api/recommendations.ts web/src/routes/recommendations/index.tsx web/src/router.tsx web/src/components/layout/Sidebar.tsx web/src/i18n.ts
git commit -m "feat(web): add recommendations route shell"
```

## Task 7: Recommendations Workspace UI

**Files:**
- Modify: `web/src/routes/recommendations/index.tsx`

- [ ] **Step 1: Implement watchlist form and batch generation UI**

Replace `web/src/routes/recommendations/index.tsx` with:

```tsx
import { Link } from 'react-router-dom';
import type { Dispatch, SetStateAction } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { recommendationsApi, type RecommendationBatch, type RecommendationBatchSummary } from '@/api/recommendations';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, ErrorBox } from '@/components/ui/Page';
import { getLocale, t } from '@/i18n';

function splitTickers(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(getLocale(), { hour12: false });
  } catch {
    return iso;
  }
}

export default function RecommendationsPage() {
  const qc = useQueryClient();
  const [watchlistText, setWatchlistText] = useState('');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);

  const watchlist = useQuery({
    queryKey: ['recommendations', 'watchlist'],
    queryFn: recommendationsApi.watchlist,
  });
  const batches = useQuery({
    queryKey: ['recommendations', 'batches'],
    queryFn: recommendationsApi.batches,
  });
  const activeBatch = useQuery({
    queryKey: ['recommendations', 'batch', activeBatchId],
    queryFn: () => recommendationsApi.batch(activeBatchId!),
    enabled: !!activeBatchId,
  });

  useEffect(() => {
    if (watchlist.data) setWatchlistText(watchlist.data.tickers.join(', '));
  }, [watchlist.data]);

  useEffect(() => {
    if (!activeBatchId && batches.data?.[0]) setActiveBatchId(batches.data[0].batch_id);
  }, [activeBatchId, batches.data]);

  const saveWatchlist = useMutation({
    mutationFn: () => recommendationsApi.saveWatchlist(splitTickers(watchlistText)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recommendations', 'watchlist'] }),
  });

  const generate = useMutation({
    mutationFn: recommendationsApi.generate,
    onSuccess: (batch) => {
      setActiveBatchId(batch.batch_id);
      setSelected({});
      qc.invalidateQueries({ queryKey: ['recommendations', 'batches'] });
      qc.setQueryData(['recommendations', 'batch', batch.batch_id], batch);
    },
  });

  const analyze = useMutation({
    mutationFn: (itemIds: string[]) => recommendationsApi.analyze(activeBatchId!, itemIds),
    onSuccess: () => {
      setSelected({});
      qc.invalidateQueries({ queryKey: ['recommendations', 'batches'] });
      qc.invalidateQueries({ queryKey: ['recommendations', 'batch', activeBatchId] });
    },
  });

  const batch = activeBatch.data;
  const selectedIds = useMemo(
    () => Object.entries(selected).filter(([, value]) => value).map(([id]) => id),
    [selected],
  );
  const error = (saveWatchlist.error || generate.error || analyze.error) as ApiError | undefined;

  return (
    <div className="space-y-4">
      <div>
        <Subheader>{t('recommendations.title')}</Subheader>
        <Caption>{t('recommendations.caption')}</Caption>
      </div>

      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="font-semibold">{t('recommendations.watchlist')}</div>
          {watchlist.data?.updated_at && (
            <div className="text-xs text-muted">{fmtTime(watchlist.data.updated_at)}</div>
          )}
        </div>
        <textarea
          className="input min-h-24 font-mono"
          value={watchlistText}
          onChange={(e) => setWatchlistText(e.target.value)}
          placeholder="AAPL, MSFT, NVDA, TSLA, GOOGL"
        />
        <div className="flex justify-end">
          <button className="btn-ghost" disabled={saveWatchlist.isPending} onClick={() => saveWatchlist.mutate()}>
            {t('recommendations.save_watchlist')}
          </button>
        </div>
      </section>

      <section className="flex items-center justify-between gap-3">
        <button className="btn-primary" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? t('recommendations.generating') : t('recommendations.generate')}
        </button>
        {batch && (
          <button className="btn-primary" disabled={!selectedIds.length || analyze.isPending} onClick={() => analyze.mutate(selectedIds)}>
            {t('recommendations.start_analysis')}
          </button>
        )}
      </section>

      {error && (
        <ErrorBox>
          <span>{error.status} · {error.detail}</span>
          {error.status === 409 && <Link to="/settings/model" className="text-[#ff4b4b] ml-2">{t('analysis.configure_model')}</Link>}
        </ErrorBox>
      )}

      {analyze.data && (
        <div className="card text-sm">
          {analyze.data.created.map((row) => (
            <div key={row.item_id} className="text-success">
              {row.ticker} → <Link to={`/analysis/${row.run_id}`} className="text-[#ff4b4b]">{row.run_id}</Link>
            </div>
          ))}
          {analyze.data.failed.map((row) => (
            <div key={row.item_id} className="text-danger">
              {row.ticker ?? row.item_id}: {row.detail}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
        <CurrentBatch batch={batch} selected={selected} setSelected={setSelected} />
        <History batches={batches.data ?? []} activeBatchId={activeBatchId} setActiveBatchId={setActiveBatchId} />
      </div>
    </div>
  );
}

function CurrentBatch({
  batch,
  selected,
  setSelected,
}: {
  batch?: RecommendationBatch;
  selected: Record<string, boolean>;
  setSelected: Dispatch<SetStateAction<Record<string, boolean>>>;
}) {
  if (!batch) return <div className="card text-muted text-sm">{t('common.empty')}</div>;
  return (
    <section className="card overflow-x-auto">
      <table className="df">
        <thead>
          <tr>
            <th></th>
            <th>{t('table.ticker')}</th>
            <th>{t('recommendations.priority')}</th>
            <th>{t('recommendations.reason')}</th>
            <th>{t('recommendations.risk')}</th>
            <th>Status</th>
            <th>Run</th>
          </tr>
        </thead>
        <tbody>
          {batch.items.map((item) => (
            <tr key={item.item_id}>
              <td>
                <input
                  type="checkbox"
                  disabled={item.status !== 'recommended'}
                  checked={Boolean(selected[item.item_id])}
                  onChange={(e) => setSelected((s) => ({ ...s, [item.item_id]: e.target.checked }))}
                />
              </td>
              <td>
                <div className="font-mono font-semibold">{item.ticker}</div>
                <div className="text-xs text-muted">{t(`recommendations.source.${item.source}`)}</div>
              </td>
              <td>{item.priority}</td>
              <td>{item.reason}</td>
              <td>{item.risk}</td>
              <td>{item.status}</td>
              <td>{item.run_id ? <Link to={`/analysis/${item.run_id}`} className="text-[#ff4b4b]">{item.run_id}</Link> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function History({
  batches,
  activeBatchId,
  setActiveBatchId,
}: {
  batches: RecommendationBatchSummary[];
  activeBatchId: string | null;
  setActiveBatchId: (id: string) => void;
}) {
  return (
    <section className="card">
      <div className="font-semibold mb-3">{t('recommendations.history')}</div>
      <div className="space-y-2">
        {batches.map((batch) => (
          <button
            key={batch.batch_id}
            className={`btn-ghost btn-block justify-start ${activeBatchId === batch.batch_id ? 'border-[#ff4b4b]' : ''}`}
            onClick={() => setActiveBatchId(batch.batch_id)}
          >
            <span className="text-left">
              <span className="block font-mono text-xs">{batch.batch_id}</span>
              <span className="block text-xs text-muted">{fmtTime(batch.created_at)} · {batch.item_count}</span>
            </span>
          </button>
        ))}
        {batches.length === 0 && <div className="text-sm text-muted">{t('common.empty')}</div>}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Run frontend typecheck**

Run:

```bash
pnpm typecheck
```

from `web/`.

Expected: `tsc --noEmit` exits 0.

- [ ] **Step 3: Run frontend build**

Run:

```bash
pnpm build
```

from `web/`.

Expected: Vite build exits 0. A chunk-size warning is acceptable if it matches the existing warning pattern.

- [ ] **Step 4: Commit recommendations page**

```bash
git add web/src/routes/recommendations/index.tsx
git commit -m "feat(web): build recommendations workspace"
```

## Task 8: Final Verification

**Files:**
- No planned code changes unless verification exposes an issue.

- [ ] **Step 1: Run recommendation backend tests**

Run:

```bash
.venv/bin/python -m pytest tests/api/test_recommendation_repository.py tests/api/test_recommendation_service.py tests/api/test_recommendation_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
.venv/bin/python -m pytest
```

Expected: all existing tests pass. A skipped live provider test is acceptable if it matches the existing DeepSeek live skip.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd web
pnpm typecheck
pnpm build
```

Expected: both commands exit 0.

- [ ] **Step 4: Check git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only stock recommendation implementation files are modified in this task set. Webull or unrelated broker changes must remain untouched unless explicitly requested.

- [ ] **Step 5: Finish with no unrelated changes**

If verification exposes an issue, return to the task that introduced the failing file, make the smallest fix there, rerun the failing command, and commit using that task's exact `git add` command. Do not add Webull or unrelated broker files.

If no fixes were needed, do not create an empty commit.
