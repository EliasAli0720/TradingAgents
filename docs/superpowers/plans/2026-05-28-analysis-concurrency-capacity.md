# Analysis Concurrency Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build production-grade analysis concurrency so each user can have up to 5 running runs, the system can have up to 100 running runs, and excess work is queued fairly.

**Architecture:** `POST /runs` becomes enqueue-only. A dispatcher owns fair capacity-based dispatch into Celery. Workers run with heartbeat, run_id-isolated artifacts/checkpoints, DB-backed memory, Redis provider limits, cooperative cancellation, and event delivery that can scale beyond DB polling.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, LangGraph, React/Vite.

---

## File Map

- Modify `tradingagents/api/config.py`: add concurrency, dispatch, heartbeat, artifact, and provider limit settings.
- Modify `tradingagents/api/models.py`: add run capacity fields, artifact model, and DB memory model.
- Modify `tradingagents/api/db.py`: additive schema migration for new columns/tables.
- Modify `tradingagents/api/repositories.py`: add queue counts, dispatch claim, heartbeat, stale-run repair, artifact, and memory repository helpers.
- Create `tradingagents/api/capacity.py`: capacity decisions and queue position calculation.
- Create `tradingagents/api/artifacts.py`: local artifact store and metadata persistence helpers.
- Create `tradingagents/api/memory_repository.py`: DB-backed memory store used by graph execution.
- Create `tradingagents/worker/dispatcher.py`: fair dispatcher loop and one-shot dispatch function.
- Create `tradingagents/worker/heartbeat.py`: worker heartbeat context.
- Create `tradingagents/worker/cancellation.py`: `CancellationToken` and `AnalysisCancelled`.
- Create `tradingagents/worker/provider_limits.py`: Redis-backed provider limiter.
- Create `tradingagents/worker/context.py`: `RunContext` container.
- Modify `tradingagents/worker/jobs.py`: execute only dispatching/running runs, heartbeat, cancellation, artifact/result/memory writes.
- Modify `tradingagents/worker/analysis.py`: accept `RunContext`, pass it into `TradingAgentsGraph`, and return artifact metadata.
- Modify `tradingagents/graph/trading_graph.py`: accept run context, use DB memory, run_id checkpoint namespace, cancellation checks, and artifact paths.
- Modify `tradingagents/graph/checkpointer.py`: support run_id checkpoint DB path and thread id.
- Modify `tradingagents/reports.py`: save reports through artifact store under run_id.
- Modify `tradingagents/api/routers/runs.py`: create queued-only runs, return queue position, support cancelling/cancelling state, list artifacts.
- Create `tradingagents/api/routers/capacity.py`: expose admin capacity endpoint.
- Modify `tradingagents/api/app.py`: include capacity/artifact routes and start optional dispatcher/sweeper process only when configured.
- Modify `tradingagents/worker/celery_app.py`: set prefetch, late ack, reject-on-worker-lost, soft/hard limits.
- Modify `start.sh` and `docker-compose.yml`: add dispatcher process and configurable worker concurrency.
- Modify `web/src/api/runs.ts`: include `queue_position`, new statuses, artifacts, and capacity response types.
- Modify `web/src/components/run/RunProgress.tsx`: show queued position, dispatching, cancelling, requeued.
- Modify `web/src/routes/analysis/detail.tsx`: render artifact links and queue state.
- Add tests under `tests/api/`, `tests/worker/`, and `tests/graph/`.

## Task 1: Capacity Settings And Schema

**Files:**
- Modify: `tradingagents/api/config.py`
- Modify: `tradingagents/api/models.py`
- Modify: `tradingagents/api/db.py`
- Test: `tests/api/test_config.py`
- Test: `tests/api/test_repositories.py`

- [ ] **Step 1: Write config tests**

Add to `tests/api/test_config.py`:

```python
def test_concurrency_capacity_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RUNNING_SYSTEM", "100")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RUNNING_PER_USER", "5")
    monkeypatch.setenv("TRADINGAGENTS_MAX_QUEUED_PER_USER", "50")
    monkeypatch.setenv("TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("TRADINGAGENTS_RUN_LEASE_SECONDS", "600")
    monkeypatch.setenv("TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS", "10")
    monkeypatch.setenv("TRADINGAGENTS_WORKER_STALE_AFTER_SECONDS", "90")

    settings = get_api_settings()

    assert settings.max_running_system == 100
    assert settings.max_running_per_user == 5
    assert settings.max_queued_per_user == 50
    assert settings.dispatch_interval_seconds == 1
    assert settings.run_lease_seconds == 600
    assert settings.worker_heartbeat_seconds == 10
    assert settings.worker_stale_after_seconds == 90
```

- [ ] **Step 2: Write schema tests**

Add to `tests/api/test_repositories.py`:

```python
def test_analysis_run_capacity_columns_exist():
    session = _session()
    repo = AnalysisRunRepository(session)

    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={"llm_provider": "openai"},
    )
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.priority == 0
    assert saved.attempt_count == 0
    assert saved.max_attempts == 2
    assert saved.current_phase is None
    assert saved.progress_percent is None
    assert saved.dispatched_at is None
    assert saved.heartbeat_at is None
    assert saved.lease_expires_at is None
    assert saved.updated_at is not None
```

Add artifact/memory model assertions:

```python
def test_artifact_and_memory_models_persist():
    session = _session()
    now = datetime.now(timezone.utc)
    run = AnalysisRun(
        run_id="run_schema",
        status="queued",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_1",
        llm_config={},
        current_step=None,
        celery_task_id=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.add(AnalysisRunArtifact(
        artifact_id="art_1",
        run_id="run_schema",
        kind="report_md",
        storage_backend="local",
        storage_key="artifacts/run_schema/reports/complete_report.md",
        content_type="text/markdown",
        size_bytes=12,
        sha256="abc",
        created_at=now,
    ))
    session.add(AnalysisMemoryEntry(
        user_id="usr_1",
        run_id="run_schema",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        rating="Hold",
        decision_markdown="Rating: Hold",
        pending=True,
        created_at=now,
    ))
    session.commit()

    assert session.get(AnalysisRunArtifact, "art_1").run_id == "run_schema"
    assert session.query(AnalysisMemoryEntry).one().ticker == "NVDA"
```

- [ ] **Step 3: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_config.py::test_concurrency_capacity_settings_read_from_env tests/api/test_repositories.py::test_analysis_run_capacity_columns_exist tests/api/test_repositories.py::test_artifact_and_memory_models_persist -q
```

Expected: failures for missing settings/model fields/classes.

- [ ] **Step 4: Implement settings and models**

In `tradingagents/api/config.py`, extend `ApiSettings`:

```python
max_running_system: int = 100
max_running_per_user: int = 5
max_queued_per_user: int = 50
dispatch_interval_seconds: int = 1
run_lease_seconds: int = 600
worker_heartbeat_seconds: int = 10
worker_stale_after_seconds: int = 90
```

In `get_api_settings()`, set them from env vars with the defaults above.

In `tradingagents/api/models.py`, add fields to `AnalysisRun`:

```python
priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
current_phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
progress_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Add `AnalysisRunArtifact` and `AnalysisMemoryEntry` classes matching the test fields.

In `tradingagents/api/db.py`, extend `ensure_additive_schema()` with additive `ALTER TABLE analysis_runs ADD COLUMN ...` statements and `Base.metadata.create_all(engine)` already creates new tables for fresh DBs.

- [ ] **Step 5: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_config.py tests/api/test_repositories.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/config.py tradingagents/api/models.py tradingagents/api/db.py tests/api/test_config.py tests/api/test_repositories.py
git commit -m "feat(api): add analysis capacity schema"
```

## Task 2: Capacity Repository And Queued-Only Creation

**Files:**
- Create: `tradingagents/api/capacity.py`
- Modify: `tradingagents/api/repositories.py`
- Modify: `tradingagents/api/routers/runs.py`
- Modify: `tradingagents/api/schemas.py`
- Test: `tests/api/test_capacity.py`
- Test: `tests/api/test_runs_routes.py`

- [ ] **Step 1: Write capacity tests**

Create `tests/api/test_capacity.py`:

```python
from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.capacity import CapacityConfig, capacity_snapshot
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


def test_capacity_snapshot_counts_user_and_system_states():
    session, repo = _repo()
    for i in range(3):
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config={})
        run.status = "running"
    for i in range(2):
        repo.create_run("AAPL", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config={})
    run = repo.create_run("MSFT", date(2026, 1, 15), "stock", ["market"], user_id="usr_2", llm_config={})
    run.status = "dispatching"
    session.commit()

    snap = capacity_snapshot(session, "usr_1", CapacityConfig(system_running=100, user_running=5, user_backlog=50))

    assert snap.system_active == 4
    assert snap.user_active == 3
    assert snap.user_backlog == 5
    assert snap.can_create is True
```

- [ ] **Step 2: Write queued-only route test**

In `tests/api/test_runs_routes.py`, add:

```python
def test_create_run_only_queues_and_does_not_enqueue_celery(client, app):
    calls = []
    app.dependency_overrides[get_task_enqueue] = lambda: lambda run_id: calls.append(run_id)

    login_as_admin(client)
    response = client.post("/runs", json={
        "ticker": "NVDA",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "analysts": ["market"],
    })

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["queue_position"] >= 1
    assert calls == []
```

- [ ] **Step 3: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_capacity.py tests/api/test_runs_routes.py::test_create_run_only_queues_and_does_not_enqueue_celery -q
```

Expected: missing capacity module and route still enqueues Celery.

- [ ] **Step 4: Implement capacity and queued-only create**

Create `tradingagents/api/capacity.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun


ACTIVE = ("dispatching", "running")
BACKLOG = ("queued", "dispatching", "running")


@dataclass(frozen=True)
class CapacityConfig:
    system_running: int
    user_running: int
    user_backlog: int


@dataclass(frozen=True)
class CapacitySnapshot:
    system_active: int
    user_active: int
    user_backlog: int
    can_create: bool


def _count(session: Session, *conditions) -> int:
    stmt = select(func.count()).select_from(AnalysisRun).where(*conditions)
    return int(session.scalar(stmt) or 0)


def capacity_snapshot(session: Session, user_id: str, config: CapacityConfig) -> CapacitySnapshot:
    system_active = _count(session, AnalysisRun.status.in_(ACTIVE))
    user_active = _count(session, AnalysisRun.user_id == user_id, AnalysisRun.status.in_(ACTIVE))
    user_backlog = _count(session, AnalysisRun.user_id == user_id, AnalysisRun.status.in_(BACKLOG))
    return CapacitySnapshot(
        system_active=system_active,
        user_active=user_active,
        user_backlog=user_backlog,
        can_create=user_backlog < config.user_backlog + config.user_running,
    )
```

Modify `CreateRunResponse` in `tradingagents/api/schemas.py` to include:

```python
queue_position: int | None = None
```

Modify `create_run()` in `tradingagents/api/routers/runs.py`:

```python
settings = get_api_settings()
snap = capacity_snapshot(
    session,
    user.user_id,
    CapacityConfig(
        system_running=settings.max_running_system,
        user_running=settings.max_running_per_user,
        user_backlog=settings.max_queued_per_user,
    ),
)
if not snap.can_create:
    raise HTTPException(status_code=429, detail="too many queued analysis runs")
...
session.commit()
position = repo.queue_position(run.run_id)
return CreateRunResponse(run_id=run.run_id, status="queued", queue_position=position)
```

Add `queue_position()` to `AnalysisRunRepository`, counting queued runs ordered by priority/created_at up to the run.

- [ ] **Step 5: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_capacity.py tests/api/test_runs_routes.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/capacity.py tradingagents/api/repositories.py tradingagents/api/routers/runs.py tradingagents/api/schemas.py tests/api/test_capacity.py tests/api/test_runs_routes.py
git commit -m "feat(api): queue analysis runs before dispatch"
```

## Task 3: Fair Dispatcher

**Files:**
- Create: `tradingagents/worker/dispatcher.py`
- Modify: `tradingagents/api/repositories.py`
- Test: `tests/worker/test_dispatcher.py`

- [ ] **Step 1: Write dispatcher tests**

Create `tests/worker/test_dispatcher.py`:

```python
from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.dispatcher import DispatchConfig, dispatch_once


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


def test_dispatcher_starts_at_most_five_runs_for_one_user():
    session, repo = _repo()
    for _ in range(8):
        repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config={})
    session.commit()
    enqueued = []

    dispatch_once(session, lambda run_id: enqueued.append(run_id), DispatchConfig(system_running=100, user_running=5, lease_seconds=600))

    assert len(enqueued) == 5
    statuses = [run.status for run in repo.list_runs_for_user("usr_1")]
    assert statuses.count("dispatching") == 5
    assert statuses.count("queued") == 3


def test_dispatcher_fairly_dispatches_across_users():
    session, repo = _repo()
    for _ in range(10):
        repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_a", llm_config={})
    repo.create_run("AAPL", date(2026, 1, 15), "stock", ["market"], user_id="usr_b", llm_config={})
    session.commit()
    enqueued = []

    dispatch_once(session, lambda run_id: enqueued.append(run_id), DispatchConfig(system_running=2, user_running=5, lease_seconds=600))

    users = [repo.get_run(run_id).user_id for run_id in enqueued]
    assert users == ["usr_a", "usr_b"]
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_dispatcher.py -q
```

Expected: missing dispatcher and repository helper methods.

- [ ] **Step 3: Implement dispatcher**

Create `tradingagents/worker/dispatcher.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from sqlalchemy.orm import Session

from tradingagents.api.repositories import AnalysisRunRepository, utcnow


@dataclass(frozen=True)
class DispatchConfig:
    system_running: int
    user_running: int
    lease_seconds: int


def dispatch_once(session: Session, enqueue: Callable[[str], str | None], config: DispatchConfig) -> int:
    repo = AnalysisRunRepository(session)
    dispatched = 0
    capacity_left = config.system_running - repo.count_active_runs()
    if capacity_left <= 0:
        return 0

    for user_id in repo.users_with_queued_runs(limit=capacity_left * 2):
        if dispatched >= capacity_left:
            break
        if repo.count_active_runs(user_id=user_id) >= config.user_running:
            continue
        run = repo.claim_next_queued_for_dispatch(
            user_id=user_id,
            lease_expires_at=utcnow() + timedelta(seconds=config.lease_seconds),
        )
        if run is None:
            continue
        task_id = enqueue(run.run_id)
        if task_id:
            repo.set_celery_task_id(run.run_id, task_id)
        dispatched += 1
    session.commit()
    return dispatched
```

Add repository methods:

- `count_active_runs(user_id: str | None = None) -> int`
- `users_with_queued_runs(limit: int) -> list[str]`
- `claim_next_queued_for_dispatch(user_id: str, lease_expires_at: datetime) -> AnalysisRun | None`
- `list_runs_for_user(user_id: str) -> list[AnalysisRun]`

`claim_next_queued_for_dispatch()` sets `status="dispatching"`, `dispatched_at=now`, `lease_expires_at=...`, and emits `run_dispatching`.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_dispatcher.py tests/api/test_repositories.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/dispatcher.py tradingagents/api/repositories.py tests/worker/test_dispatcher.py
git commit -m "feat(worker): dispatch analysis runs fairly"
```

## Task 4: Worker Heartbeat And Sweeper

**Files:**
- Create: `tradingagents/worker/heartbeat.py`
- Create: `tradingagents/worker/sweeper.py`
- Modify: `tradingagents/worker/jobs.py`
- Modify: `tradingagents/api/repositories.py`
- Test: `tests/worker/test_jobs.py`
- Test: `tests/worker/test_sweeper.py`

- [ ] **Step 1: Write heartbeat/sweeper tests**

Add to `tests/worker/test_jobs.py`:

```python
def test_execute_analysis_run_requires_dispatched_run():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG)
    session.commit()

    execute_analysis_run(repo, run.run_id, lambda *args: {"decision": "Hold", "reports": {}, "final_state": {}})

    assert repo.get_run(run.run_id).status == "queued"
    assert repo.get_result(run.run_id) is None
```

Create `tests/worker/test_sweeper.py`:

```python
from datetime import date, timedelta

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository, utcnow
from tradingagents.worker.sweeper import sweep_once


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


def test_sweeper_requeues_expired_dispatching_run():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config={})
    run.status = "dispatching"
    run.lease_expires_at = utcnow() - timedelta(seconds=1)
    session.commit()

    sweep_once(session, stale_after_seconds=90)

    saved = repo.get_run(run.run_id)
    assert saved.status == "queued"
    assert saved.celery_task_id is None
    assert repo.list_events(run.run_id)[-1].event_type == "run_requeued"


def test_sweeper_fails_stale_running_after_attempts_exhausted():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config={})
    run.status = "running"
    run.attempt_count = run.max_attempts
    run.heartbeat_at = utcnow() - timedelta(seconds=120)
    session.commit()

    sweep_once(session, stale_after_seconds=90)

    assert repo.get_run(run.run_id).status == "failed"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_jobs.py::test_execute_analysis_run_requires_dispatched_run tests/worker/test_sweeper.py -q
```

Expected: worker still claims queued directly and sweeper does not exist.

- [ ] **Step 3: Implement heartbeat/sweeper**

Create `tradingagents/worker/heartbeat.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from threading import Event, Thread
from time import sleep

from tradingagents.api.db import SessionLocal
from tradingagents.api.repositories import AnalysisRunRepository


@contextmanager
def heartbeat(run_id: str, interval_seconds: int):
    stopped = Event()

    def _beat():
        while not stopped.wait(interval_seconds):
            with SessionLocal() as session:
                repo = AnalysisRunRepository(session)
                repo.record_heartbeat(run_id)
                session.commit()

    thread = Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=interval_seconds)
```

Create `tradingagents/worker/sweeper.py` with `sweep_once(session, stale_after_seconds)` that repairs expired `dispatching`, stale `running`, and stale `cancelling`.

Modify `execute_analysis_run()` so it only starts `dispatching` runs via `repo.start_dispatched_run(run_id)`.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_jobs.py tests/worker/test_sweeper.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/heartbeat.py tradingagents/worker/sweeper.py tradingagents/worker/jobs.py tradingagents/api/repositories.py tests/worker/test_jobs.py tests/worker/test_sweeper.py
git commit -m "feat(worker): add run heartbeat and sweeper"
```

## Task 5: Run-ID Artifact Store

**Files:**
- Create: `tradingagents/api/artifacts.py`
- Modify: `tradingagents/reports.py`
- Modify: `tradingagents/worker/analysis.py`
- Modify: `tradingagents/worker/jobs.py`
- Modify: `tradingagents/api/repositories.py`
- Test: `tests/api/test_artifacts.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write artifact tests**

Create `tests/api/test_artifacts.py`:

```python
from tradingagents.api.artifacts import LocalArtifactStore


def test_local_artifact_store_writes_under_run_id(tmp_path):
    store = LocalArtifactStore(tmp_path)

    artifact = store.write_text(
        run_id="run_abc",
        kind="report_md",
        relative_path="reports/complete_report.md",
        content="hello",
        content_type="text/markdown",
    )

    assert artifact.storage_key == "run_abc/reports/complete_report.md"
    assert (tmp_path / artifact.storage_key).read_text() == "hello"
    assert artifact.size_bytes == 5
    assert artifact.sha256
```

Add to `tests/worker/test_jobs.py`:

```python
def test_successful_worker_persists_report_artifact_metadata(tmp_path):
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1", llm_config=LLM_CONFIG)
    run.status = "dispatching"
    session.commit()

    def fake_executor(*args, **kwargs):
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": "NVDA", "final_trade_decision": "Rating: Hold"},
            "artifacts": [{"kind": "report_md", "storage_key": "run_x/reports/complete_report.md"}],
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    artifacts = repo.list_artifacts(run.run_id)
    assert [artifact.kind for artifact in artifacts] == ["report_md"]
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_artifacts.py tests/worker/test_jobs.py::test_successful_worker_persists_report_artifact_metadata -q
```

Expected: missing artifact store and repository methods.

- [ ] **Step 3: Implement artifact store**

Create `LocalArtifactStore` with `write_text()` and `write_json()` returning a dataclass:

```python
@dataclass(frozen=True)
class ArtifactWrite:
    kind: str
    storage_backend: str
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str
```

Modify `save_analysis_report()` to accept `run_id` and `artifact_store`, write every report file through artifact store, and return artifact writes.

Modify worker success path to persist artifact metadata via `repo.add_artifact(...)`.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_artifacts.py tests/worker/test_jobs.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/artifacts.py tradingagents/reports.py tradingagents/worker/analysis.py tradingagents/worker/jobs.py tradingagents/api/repositories.py tests/api/test_artifacts.py tests/worker/test_jobs.py
git commit -m "feat(api): isolate analysis artifacts by run"
```

## Task 6: DB Memory Store

**Files:**
- Create: `tradingagents/api/memory_repository.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/worker/context.py`
- Test: `tests/api/test_memory_repository.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write DB memory tests**

Create `tests/api/test_memory_repository.py`:

```python
from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.memory_repository import AnalysisMemoryRepository


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisMemoryRepository(session)


def test_memory_repository_returns_same_ticker_and_cross_ticker_context():
    session, repo = _repo()
    repo.store_decision("usr_1", "run_1", "NVDA", date(2026, 1, 15), "Rating: Hold", pending=False, reflection="Worked.")
    repo.store_decision("usr_1", "run_2", "AAPL", date(2026, 1, 16), "Rating: Buy", pending=False, reflection="Good.")
    session.commit()

    context = repo.get_past_context("usr_1", "NVDA")

    assert "Past analyses of NVDA" in context
    assert "Recent cross-ticker lessons" in context
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_memory_repository.py -q
```

Expected: missing memory repository.

- [ ] **Step 3: Implement DB memory repository**

Create `AnalysisMemoryRepository` with:

- `store_decision(user_id, run_id, ticker, trade_date, decision_markdown, pending=True, reflection=None)`
- `get_past_context(user_id, ticker, n_same=5, n_cross=3)`
- `lock_pending_for_ticker(user_id, ticker)`
- `resolve_pending(entry_id, raw_return, alpha_return, holding_days, reflection)`

Modify `TradingAgentsGraph` to use `context.memory_store` when context is present, while keeping `TradingMemoryLog` as CLI fallback.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_memory_repository.py tests/worker/test_jobs.py tests/test_memory_log.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/memory_repository.py tradingagents/graph/trading_graph.py tradingagents/worker/context.py tests/api/test_memory_repository.py tests/worker/test_jobs.py
git commit -m "feat(api): store analysis memory in database"
```

## Task 7: Run Context, Checkpoints, And Cancellation

**Files:**
- Create: `tradingagents/worker/context.py`
- Create: `tradingagents/worker/cancellation.py`
- Modify: `tradingagents/graph/checkpointer.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/api/routers/runs.py`
- Test: `tests/graph/test_run_context.py`
- Test: `tests/worker/test_cancellation.py`

- [ ] **Step 1: Write cancellation tests**

Create `tests/worker/test_cancellation.py`:

```python
import pytest

from tradingagents.worker.cancellation import AnalysisCancelled, CancellationToken


def test_cancellation_token_raises_when_cancelled():
    token = CancellationToken(lambda: True)

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_cancellation_token_allows_when_not_cancelled():
    token = CancellationToken(lambda: False)

    token.raise_if_cancelled()
```

Create `tests/graph/test_run_context.py`:

```python
from tradingagents.graph.checkpointer import run_thread_id


def test_run_thread_id_uses_run_id():
    assert run_thread_id("run_abc") == "run_abc"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_cancellation.py tests/graph/test_run_context.py -q
```

Expected: missing cancellation token and run checkpoint helper.

- [ ] **Step 3: Implement context/cancellation/checkpoint namespace**

Create `tradingagents/worker/cancellation.py`:

```python
class AnalysisCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self, is_cancelled):
        self._is_cancelled = is_cancelled

    def raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise AnalysisCancelled()
```

Create `RunContext` dataclass in `tradingagents/worker/context.py`.

In `tradingagents/graph/checkpointer.py`, add:

```python
def run_thread_id(run_id: str) -> str:
    return run_id
```

Modify graph setup to wrap each node with a cancellable wrapper when context is present:

```python
def cancellable_node(name, fn, token):
    def _wrapped(state):
        token.raise_if_cancelled()
        result = fn(state)
        token.raise_if_cancelled()
        return result
    return _wrapped
```

Modify cancel route so running/dispatching transitions to `cancelling`, writes event `run_cancelling`, and sets the Redis cancel flag.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_cancellation.py tests/graph/test_run_context.py tests/worker/test_jobs.py tests/api/test_runs_routes.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/context.py tradingagents/worker/cancellation.py tradingagents/graph/checkpointer.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tradingagents/api/routers/runs.py tests/worker/test_cancellation.py tests/graph/test_run_context.py
git commit -m "feat(graph): add run context cancellation"
```

## Task 8: Provider Limiter

**Files:**
- Create: `tradingagents/worker/provider_limits.py`
- Modify: `tradingagents/llm_clients/factory.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Test: `tests/worker/test_provider_limits.py`

- [ ] **Step 1: Write provider limiter tests**

Create `tests/worker/test_provider_limits.py`:

```python
import pytest

from tradingagents.worker.provider_limits import InMemoryProviderLimiter, ProviderLimitExceeded


def test_provider_limiter_rejects_when_concurrent_limit_reached():
    limiter = InMemoryProviderLimiter({"openai": 1})

    with limiter.acquire("openai"):
        with pytest.raises(ProviderLimitExceeded):
            with limiter.acquire("openai", wait_seconds=0):
                pass


def test_provider_limiter_releases_after_context():
    limiter = InMemoryProviderLimiter({"openai": 1})

    with limiter.acquire("openai"):
        pass

    with limiter.acquire("openai", wait_seconds=0):
        pass
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_provider_limits.py -q
```

Expected: missing provider limiter.

- [ ] **Step 3: Implement limiter and integration hooks**

Create `ProviderLimiter` interface with `acquire(provider, wait_seconds=30)`.

Implement `InMemoryProviderLimiter` for unit tests and `RedisProviderLimiter` for production.

Integrate at LLM factory boundary by wrapping LLM invoke methods, and at data tool boundary by wrapping tool functions when a `RunContext.provider_limiter` is present.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/worker/test_provider_limits.py tests/test_model_validation.py tests/test_dataflows_config.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/provider_limits.py tradingagents/llm_clients/factory.py tradingagents/agents/utils/agent_utils.py tests/worker/test_provider_limits.py
git commit -m "feat(worker): limit provider concurrency"
```

## Task 9: Redis Pub/Sub SSE With DB Replay

**Files:**
- Create: `tradingagents/api/events.py`
- Modify: `tradingagents/api/repositories.py`
- Modify: `tradingagents/api/routers/runs.py`
- Test: `tests/api/test_sse_events.py`

- [ ] **Step 1: Write event publisher tests**

Add to `tests/api/test_sse_events.py`:

```python
def test_event_publisher_persists_and_publishes(monkeypatch):
    published = []

    class FakeRedis:
        def publish(self, channel, payload):
            published.append((channel, payload))

    publisher = RunEventPublisher(FakeRedis())
    publisher.publish("run_1", "run_progress", {"phase": "analyst_market"})

    assert published[0][0] == "run:run_1"
    assert "run_progress" in published[0][1]
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_sse_events.py::test_event_publisher_persists_and_publishes -q
```

Expected: missing event publisher.

- [ ] **Step 3: Implement DB replay + Redis live stream**

Create `RunEventPublisher` that publishes JSON to `run:{run_id}` after DB event persistence.

Modify SSE endpoint:

- read `Last-Event-ID`
- replay DB events after that id
- subscribe to Redis pub/sub for live events
- stop on terminal event

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_sse_events.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/events.py tradingagents/api/repositories.py tradingagents/api/routers/runs.py tests/api/test_sse_events.py
git commit -m "feat(api): stream run events through redis"
```

## Task 10: Capacity And Artifact API Surface

**Files:**
- Create: `tradingagents/api/routers/capacity.py`
- Modify: `tradingagents/api/routers/runs.py`
- Modify: `tradingagents/api/app.py`
- Modify: `tradingagents/api/schemas.py`
- Test: `tests/api/test_capacity_routes.py`
- Test: `tests/api/test_runs_routes.py`

- [ ] **Step 1: Write route tests**

Create `tests/api/test_capacity_routes.py`:

```python
def test_admin_capacity_endpoint_returns_counts(admin_client):
    response = admin_client.get("/admin/capacity")

    assert response.status_code == 200
    body = response.json()
    assert "max_running_system" in body
    assert "running_system" in body
    assert "queued_system" in body
```

Add artifact route test:

```python
def test_run_artifacts_are_owner_scoped(admin_client):
    response = admin_client.get("/runs/run_missing/artifacts")

    assert response.status_code == 404
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_capacity_routes.py tests/api/test_runs_routes.py::test_run_artifacts_are_owner_scoped -q
```

Expected: missing capacity/artifact endpoints.

- [ ] **Step 3: Implement API routes**

Add `/admin/capacity`, `/runs/{run_id}/artifacts`, and `/runs/{run_id}/artifacts/{artifact_id}`.

Responses must use scoped repository rules: admin can view all, non-admin can only view own runs.

- [ ] **Step 4: Verify task**

Run:

```bash
./.venv/bin/python -m pytest tests/api/test_capacity_routes.py tests/api/test_runs_routes.py tests/api/test_runs_authz.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/capacity.py tradingagents/api/routers/runs.py tradingagents/api/app.py tradingagents/api/schemas.py tests/api/test_capacity_routes.py tests/api/test_runs_routes.py tests/api/test_runs_authz.py
git commit -m "feat(api): expose capacity and artifacts"
```

## Task 11: Frontend Queue And Artifact UX

**Files:**
- Modify: `web/src/api/runs.ts`
- Modify: `web/src/components/run/RunProgress.tsx`
- Modify: `web/src/routes/analysis/detail.tsx`
- Modify: `web/src/routes/analysis/list.tsx`
- Test/Verify: `pnpm build`

- [ ] **Step 1: Update TypeScript types**

In `web/src/api/runs.ts`, add statuses:

```ts
export type RunStatus = 'queued' | 'dispatching' | 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled';
```

Add `queue_position?: number | null` to create response and run summary where applicable.

Add:

```ts
export type RunArtifact = {
  artifact_id: string;
  kind: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};
```

- [ ] **Step 2: Update progress UI**

In `RunProgress`, show:

- `queued`: queue position and waiting message.
- `dispatching`: capacity acquired, worker starting.
- `running`: current progress phase.
- `cancelling`: cancellation requested.
- terminal states unchanged.

- [ ] **Step 3: Add artifact links**

In `analysis/detail.tsx`, when run succeeded, call `runsApi.artifacts(runId)` and render links for `report_md` and `final_state_json`.

- [ ] **Step 4: Verify frontend**

Run:

```bash
pnpm build
```

Expected: TypeScript and Vite build pass. Existing Vite chunk-size warning is acceptable.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/runs.ts web/src/components/run/RunProgress.tsx web/src/routes/analysis/detail.tsx web/src/routes/analysis/list.tsx
git commit -m "feat(web): show queued runs and artifacts"
```

## Task 12: Deployment Wiring

**Files:**
- Modify: `tradingagents/worker/celery_app.py`
- Modify: `start.sh`
- Modify: `docker-compose.yml`
- Modify: `RUNNING.md`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Update Celery config**

In `tradingagents/worker/celery_app.py`, add:

```python
worker_prefetch_multiplier=1,
task_acks_late=True,
task_reject_on_worker_lost=True,
task_soft_time_limit=settings.task_soft_time_limit_seconds,
```

Add `task_soft_time_limit_seconds` to `ApiSettings`.

- [ ] **Step 2: Update local startup**

In `start.sh`, replace fixed worker concurrency:

```bash
--concurrency="${TRADINGAGENTS_WORKER_CONCURRENCY:-10}"
```

Start dispatcher as a separate background process:

```bash
"$VENV_PYTHON" -m tradingagents.worker.dispatcher
```

- [ ] **Step 3: Update docs**

In `RUNNING.md`, document:

```env
TRADINGAGENTS_MAX_RUNNING_SYSTEM=100
TRADINGAGENTS_MAX_RUNNING_PER_USER=5
TRADINGAGENTS_MAX_QUEUED_PER_USER=50
TRADINGAGENTS_WORKER_CONCURRENCY=10
```

- [ ] **Step 4: Verify backend and frontend**

Run:

```bash
./.venv/bin/python -m pytest tests/api tests/worker tests/graph -q
pnpm build
```

Expected: all selected Python tests pass; frontend build passes with only existing chunk warning.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/celery_app.py tradingagents/api/config.py start.sh docker-compose.yml RUNNING.md tests/worker/test_jobs.py
git commit -m "chore: wire concurrent analysis deployment"
```

## Final Verification

- [ ] Run backend tests:

```bash
./.venv/bin/python -m pytest tests/api tests/worker tests/graph -q
```

- [ ] Run targeted legacy graph tests:

```bash
./.venv/bin/python -m pytest tests/test_memory_log.py tests/test_checkpoint_resume.py tests/test_safe_ticker_component.py -q
```

- [ ] Run frontend build:

```bash
pnpm build
```

- [ ] Run manual capacity smoke:

```bash
for i in $(seq 1 8); do
  curl -s -X POST http://127.0.0.1:8000/runs \
    -H 'Content-Type: application/json' \
    -d '{"ticker":"NVDA","trade_date":"2026-01-15","asset_type":"stock","analysts":["market"]}' &
done
wait
```

Expected with `MAX_RUNNING_PER_USER=5`: five runs dispatch/running for that user, remaining runs queued.

## Self-Review

- Spec coverage: capacity, fair dispatch, state machine, heartbeat, sweeper, artifacts, DB memory, provider limiter, cancellation, SSE, API, frontend, and deployment are each mapped to tasks.
- Marker scan: no unresolved markers or open-ended implementation instructions remain.
- Type consistency: task names use `dispatching`, `cancelling`, `AnalysisRunArtifact`, `AnalysisMemoryEntry`, `RunContext`, `CancellationToken`, and `ProviderLimiter` consistently across tests and implementation steps.
