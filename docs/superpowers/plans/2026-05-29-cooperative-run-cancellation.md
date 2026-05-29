# Cooperative Run Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop cancelled running analysis jobs at graph node and stream boundaries so they do not continue consuming downstream LLM, data, or translation resources.

**Architecture:** Keep the current API cancellation state machine. Add a DB-backed `CancellationToken`, pass it through `RunContext` into `TradingAgentsGraph`, and check it before/after graph nodes and stream section callbacks. Use helper functions in the worker to avoid dispatching translation tasks after cancellation.

**Tech Stack:** Python, FastAPI worker modules, SQLAlchemy sessions, Celery task wrappers, LangGraph graph setup, pytest.

---

## File Structure

- Modify: `tradingagents/worker/cancellation.py`
  - Add `build_db_cancellation_token(session_factory, run_id)` and logging.
- Modify: `tradingagents/worker/jobs.py`
  - Pass `RunContext` into compatible executors.
  - Build DB cancellation token for production worker runs.
  - Treat `AnalysisCancelled` as normal completion.
  - Add helper for translation enqueue only when run is still active.
- Modify: `tradingagents/worker/analysis.py`
  - Accept optional `RunContext` and pass it to `TradingAgentsGraph`.
- Modify: `tradingagents/graph/trading_graph.py`
  - Add graph-level cancellation check helper.
  - Check cancellation around the stream / `on_section_ready` branch.
- Modify: `tests/worker/test_cancellation.py`
  - Cover DB-backed cancellation token behavior.
- Modify: `tests/worker/test_jobs.py`
  - Cover context propagation, cooperative worker cancellation, no result write, no failure event, translation enqueue skip.
- Modify: `tests/graph/test_run_context.py`
  - Cover graph cancellation helper and graph node wrapper behavior.

## Task 1: Add DB-Backed Cancellation Token

**Files:**
- Modify: `tradingagents/worker/cancellation.py`
- Test: `tests/worker/test_cancellation.py`

- [ ] **Step 1: Write failing tests**

Append these tests to `tests/worker/test_cancellation.py`:

```python
import logging
from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.cancellation import (
    AnalysisCancelled,
    CancellationToken,
    build_db_cancellation_token,
)


def _session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_db_cancellation_token_reads_fresh_cancelled_status_from_new_session():
    from tradingagents.api.models import AnalysisRun

    Session = _session_factory()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        session.commit()
        run_id = run.run_id

    token = build_db_cancellation_token(Session, run_id)

    with Session() as session:
        run = session.get(AnalysisRun, run_id)
        run.status = "cancelling"
        session.commit()

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_db_cancellation_token_treats_missing_run_as_cancelled():
    Session = _session_factory()
    token = build_db_cancellation_token(Session, "run_missing")

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_db_cancellation_token_does_not_cancel_on_transient_db_error(caplog):
    def broken_session_factory():
        raise RuntimeError("database unavailable")

    token = build_db_cancellation_token(broken_session_factory, "run_1")

    with caplog.at_level(logging.WARNING):
        token.raise_if_cancelled()

    assert "cancellation status check failed for run run_1" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/worker/test_cancellation.py -q
```

Expected: FAIL because `build_db_cancellation_token` is not defined.

- [ ] **Step 3: Implement DB token helper**

Update `tradingagents/worker/cancellation.py` to:

```python
from __future__ import annotations

from collections.abc import Callable
import logging

from tradingagents.api.models import AnalysisRun


logger = logging.getLogger(__name__)


class AnalysisCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self, is_cancelled: Callable[[], bool]):
        self._is_cancelled = is_cancelled

    def raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise AnalysisCancelled()


def build_db_cancellation_token(session_factory, run_id: str) -> CancellationToken:
    def is_cancelled() -> bool:
        try:
            with session_factory() as session:
                run = session.get(AnalysisRun, run_id)
                return run is None or run.status in {"cancelling", "cancelled"}
        except Exception:
            logger.warning(
                "cancellation status check failed for run %s",
                run_id,
                exc_info=True,
            )
            return False

    return CancellationToken(is_cancelled)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/worker/test_cancellation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/cancellation.py tests/worker/test_cancellation.py
git commit -m "feat(worker): add db-backed cancellation token"
```

## Task 2: Pass RunContext Through Worker Executor

**Files:**
- Modify: `tradingagents/worker/jobs.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write failing tests for executor context compatibility**

Append these tests near the existing `execute_analysis_run` tests in `tests/worker/test_jobs.py`:

```python
from tradingagents.worker.context import RunContext
from tradingagents.worker.cancellation import CancellationToken
from tradingagents.worker.jobs import _execute_with_optional_run_id


def test_execute_with_optional_run_id_passes_context_to_compatible_executor():
    captured = {}
    context = RunContext(
        run_id="run_ctx",
        user_id="usr_1",
        cancellation_token=CancellationToken(lambda: False),
    )

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config, context=None):
        captured["context"] = context
        return {"decision": "Hold", "reports": {}, "final_state": {}}

    _execute_with_optional_run_id(
        fake_executor,
        run_id="run_ctx",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        llm_config=LLM_CONFIG,
        context=context,
    )

    assert captured["context"] is context


def test_execute_with_optional_run_id_keeps_legacy_executor_compatible():
    calls = []
    context = RunContext(
        run_id="run_ctx",
        user_id="usr_1",
        cancellation_token=CancellationToken(lambda: False),
    )

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        calls.append((ticker, trade_date, asset_type, analysts, llm_config))
        return {"decision": "Hold", "reports": {}, "final_state": {}}

    _execute_with_optional_run_id(
        fake_executor,
        run_id="run_ctx",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        llm_config=LLM_CONFIG,
        context=context,
    )

    assert calls == [("NVDA", date(2026, 1, 15), "stock", ["market"], LLM_CONFIG)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/worker/test_jobs.py::test_execute_with_optional_run_id_passes_context_to_compatible_executor tests/worker/test_jobs.py::test_execute_with_optional_run_id_keeps_legacy_executor_compatible -q
```

Expected: FAIL because `_execute_with_optional_run_id` does not accept `context`.

- [ ] **Step 3: Implement context passthrough**

In `tradingagents/worker/jobs.py`, update imports and signatures:

```python
from tradingagents.api.memory_repository import AnalysisMemoryRepository
from tradingagents.worker.cancellation import AnalysisCancelled, build_db_cancellation_token
from tradingagents.worker.context import RunContext
```

Change `AnalysisExecutor` to:

```python
AnalysisExecutor = Callable[..., dict[str, Any]]
```

Update `_execute_with_optional_run_id`:

```python
def _execute_with_optional_run_id(
    executor: AnalysisExecutor,
    *,
    run_id: str,
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
    on_section=None,
    context: RunContext | None = None,
) -> dict[str, Any]:
    try:
        parameters = list(signature(executor).parameters.values())
    except (TypeError, ValueError):
        parameters = []
    has_var_kw = any(p.kind == Parameter.VAR_KEYWORD for p in parameters)
    names = {p.name for p in parameters}
    kwargs: dict[str, Any] = {}
    if has_var_kw or "run_id" in names:
        kwargs["run_id"] = run_id
    if on_section is not None and (has_var_kw or "on_section" in names):
        kwargs["on_section"] = on_section
    if context is not None and (has_var_kw or "context" in names):
        kwargs["context"] = context
    return executor(ticker, trade_date, asset_type, analysts, llm_config, **kwargs)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/worker/test_jobs.py::test_execute_with_optional_run_id_passes_context_to_compatible_executor tests/worker/test_jobs.py::test_execute_with_optional_run_id_keeps_legacy_executor_compatible -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/jobs.py tests/worker/test_jobs.py
git commit -m "feat(worker): pass run context to analysis executor"
```

## Task 3: Cooperatively Cancel Worker Runs

**Files:**
- Modify: `tradingagents/worker/jobs.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write failing cooperative cancellation test**

Append this helper and test to `tests/worker/test_jobs.py`:

```python
def _repo_with_session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return Session, session, AnalysisRunRepository(session)


def test_execute_analysis_run_stops_when_context_token_sees_cancelling_status():
    from tradingagents.api.models import AnalysisRun

    Session, session, repo = _repo_with_session_factory()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config=LLM_CONFIG,
    )
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config, context=None):
        assert context is not None
        with Session() as other_session:
            other_run = other_session.get(AnalysisRun, run.run_id)
            other_run.status = "cancelling"
            other_run.error = "user requested cancellation"
            other_session.commit()
        context.cancellation_token.raise_if_cancelled()
        raise AssertionError("executor should have been cancelled")

    execute_analysis_run(
        repo,
        run.run_id,
        fake_executor,
        cancellation_session_factory=Session,
    )
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelled"
    assert repo.get_result(run.run_id) is None
    assert "run_failed" not in [e.event_type for e in repo.list_events(run.run_id)]
    assert repo.list_events(run.run_id)[-1].event_type == "run_cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/worker/test_jobs.py::test_execute_analysis_run_stops_when_context_token_sees_cancelling_status -q
```

Expected: FAIL because `execute_analysis_run` does not accept `cancellation_session_factory` and does not create context.

- [ ] **Step 3: Implement worker context creation and normal cancellation completion**

Update `execute_analysis_run` signature:

```python
def execute_analysis_run(
    repo: AnalysisRunRepository,
    run_id: str,
    executor: AnalysisExecutor = run_tradingagents_analysis,
    heartbeat_interval_seconds: int | None = None,
    on_section=None,
    cancellation_session_factory=SessionLocal,
) -> None:
```

After the second `repo.session.commit()` following the analyzing progress record, create context:

```python
        context = RunContext(
            run_id=run_id,
            user_id=run.user_id,
            memory_store=AnalysisMemoryRepository(repo.session),
            cancellation_token=build_db_cancellation_token(
                cancellation_session_factory,
                run_id,
            ),
        )
```

Pass `context=context` into both `_execute_with_optional_run_id(...)` call sites.

Change the `except AnalysisCancelled` block to:

```python
    except AnalysisCancelled:
        repo.session.rollback()
        repo.mark_cancelled(run_id, "analysis cancelled")
        repo.session.commit()
        return
```

- [ ] **Step 4: Run worker cancellation tests**

Run:

```bash
pytest tests/worker/test_jobs.py::test_execute_analysis_run_stops_when_context_token_sees_cancelling_status tests/worker/test_jobs.py::test_execute_analysis_run_does_not_overwrite_cancelled_run_after_executor_returns -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/jobs.py tests/worker/test_jobs.py
git commit -m "feat(worker): stop analysis runs cooperatively"
```

## Task 4: Pass RunContext Into TradingAgentsGraph

**Files:**
- Modify: `tradingagents/worker/analysis.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write failing context propagation test**

Append this test near the existing `run_tradingagents_analysis` tests in `tests/worker/test_jobs.py`:

```python
def test_run_tradingagents_analysis_passes_context_to_graph(monkeypatch, tmp_path):
    from tradingagents.worker.context import RunContext
    from tradingagents.worker.cancellation import CancellationToken

    monkeypatch.setitem(
        sys.modules["tradingagents.worker.analysis"].DEFAULT_CONFIG,
        "reports_dir",
        str(tmp_path / "reports"),
    )
    captured = {}
    context = RunContext(
        run_id="run_ctx",
        user_id="usr_1",
        cancellation_token=CancellationToken(lambda: False),
    )

    class FakeGraph:
        def __init__(self, selected_analysts, config, context=None):
            captured["selected_analysts"] = selected_analysts
            captured["context"] = context

        def propagate(self, ticker, trade_date, asset_type):
            return ({"final_trade_decision": "Hold"}, "Hold")

    monkeypatch.setattr("tradingagents.worker.analysis.TradingAgentsGraph", FakeGraph)

    run_tradingagents_analysis(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        LLM_CONFIG,
        context=context,
    )

    assert captured["selected_analysts"] == ["market"]
    assert captured["context"] is context
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/worker/test_jobs.py::test_run_tradingagents_analysis_passes_context_to_graph -q
```

Expected: FAIL because `run_tradingagents_analysis` does not accept `context`.

- [ ] **Step 3: Implement analysis context parameter**

Update `tradingagents/worker/analysis.py`:

```python
from tradingagents.worker.context import RunContext
```

Change signature:

```python
def run_tradingagents_analysis(
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
    *,
    run_id: str | None = None,
    on_section=None,
    context: RunContext | None = None,
) -> dict[str, Any]:
```

Change graph construction:

```python
    graph = TradingAgentsGraph(
        selected_analysts=analysts,
        config=config,
        context=context,
    )
```

- [ ] **Step 4: Run graph context tests**

Run:

```bash
pytest tests/worker/test_jobs.py::test_run_tradingagents_analysis_passes_context_to_graph tests/worker/test_jobs.py::test_run_tradingagents_analysis_decrypts_user_api_key_snapshot -q
```

Expected: PASS. If `FakeGraph` classes in older tests reject `context`, update their constructors to accept `context=None`.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/analysis.py tests/worker/test_jobs.py
git commit -m "feat(worker): pass run context into trading graph"
```

## Task 5: Check Cancellation at Graph and Stream Boundaries

**Files:**
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/graph/test_run_context.py`

- [ ] **Step 1: Write failing graph cancellation helper tests**

Append to `tests/graph/test_run_context.py`:

```python
from types import SimpleNamespace

import pytest

from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.worker.cancellation import AnalysisCancelled, CancellationToken


def test_trading_graph_raise_if_cancelled_delegates_to_context_token():
    calls = []
    graph = object.__new__(TradingAgentsGraph)
    graph.context = SimpleNamespace(
        cancellation_token=SimpleNamespace(
            raise_if_cancelled=lambda: calls.append("checked")
        )
    )

    graph._raise_if_cancelled()

    assert calls == ["checked"]


def test_trading_graph_raise_if_cancelled_allows_missing_token():
    graph = object.__new__(TradingAgentsGraph)
    graph.context = None

    graph._raise_if_cancelled()


def test_graph_setup_cancellable_stops_before_node_execution():
    setup = object.__new__(GraphSetup)
    setup.cancellation_token = CancellationToken(lambda: True)
    executed = []

    wrapped = setup._cancellable("Node", lambda state: executed.append(state))

    with pytest.raises(AnalysisCancelled):
        wrapped({"x": 1})

    assert executed == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/graph/test_run_context.py -q
```

Expected: FAIL because `TradingAgentsGraph._raise_if_cancelled` does not exist.

- [ ] **Step 3: Implement graph helper and stream checks**

In `tradingagents/graph/trading_graph.py`, add method inside `TradingAgentsGraph`:

```python
    def _raise_if_cancelled(self) -> None:
        token = getattr(getattr(self, "context", None), "cancellation_token", None)
        if token is not None:
            token.raise_if_cancelled()
```

In `_run_graph`, inside `elif on_section_ready is not None:`, add checks:

```python
            self._raise_if_cancelled()
            final_state = {}
            seen_sections: set[str] = set()
            for chunk in self.graph.stream(init_agent_state, **args):
                self._raise_if_cancelled()
                if isinstance(chunk, dict):
                    final_state.update(chunk)
                for key in REPORT_KEYS:
                    if key in seen_sections:
                        continue
                    value = final_state.get(key)
                    if isinstance(value, str) and value.strip():
                        self._raise_if_cancelled()
                        seen_sections.add(key)
                        try:
                            on_section_ready(key, value)
                        except Exception:
                            logger.warning(
                                "on_section_ready failed for %s", key, exc_info=True
                            )
                self._raise_if_cancelled()
```

- [ ] **Step 4: Run graph tests**

Run:

```bash
pytest tests/graph/test_run_context.py tests/worker/test_cancellation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/trading_graph.py tests/graph/test_run_context.py
git commit -m "feat(graph): check cancellation at stream boundaries"
```

## Task 6: Block Translation Enqueue After Cancellation

**Files:**
- Modify: `tradingagents/worker/jobs.py`
- Test: `tests/worker/test_jobs.py`

- [ ] **Step 1: Write failing translation enqueue tests**

Append to `tests/worker/test_jobs.py`:

```python
def test_enqueue_translation_if_active_skips_cancelling_run():
    from tradingagents.worker.jobs import _enqueue_translation_if_active

    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config=LLM_CONFIG,
    )
    run.status = "cancelling"
    session.commit()
    calls = []

    _enqueue_translation_if_active(
        repo,
        run.run_id,
        "zh",
        "market_report",
        "body",
        enqueue=lambda **kwargs: calls.append(kwargs["args"]),
    )

    assert calls == []


def test_enqueue_translation_if_active_enqueues_running_run():
    from tradingagents.worker.jobs import _enqueue_translation_if_active

    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config=LLM_CONFIG,
    )
    run.status = "running"
    session.commit()
    calls = []

    _enqueue_translation_if_active(
        repo,
        run.run_id,
        "zh",
        "market_report",
        "body",
        enqueue=lambda **kwargs: calls.append(kwargs["args"]),
    )

    assert calls == [(run.run_id, "zh", "market_report", "body")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/worker/test_jobs.py::test_enqueue_translation_if_active_skips_cancelling_run tests/worker/test_jobs.py::test_enqueue_translation_if_active_enqueues_running_run -q
```

Expected: FAIL because `_enqueue_translation_if_active` does not exist.

- [ ] **Step 3: Implement active-run translation helper**

In `tradingagents/worker/jobs.py`, add:

```python
def _enqueue_translation_if_active(
    repo: AnalysisRunRepository,
    run_id: str,
    lang: str,
    section: str,
    text: str,
    *,
    enqueue=None,
) -> bool:
    repo.session.expire_all()
    run = repo.session.get(AnalysisRun, run_id)
    if run is None or run.status in {"cancelling", "cancelled"}:
        return False
    enqueue = enqueue or translate_section_task.apply_async
    enqueue(args=(run_id, lang, section, text))
    return True
```

Update `run_analysis_task()` callback:

```python
            def on_section(section: str, text: str, _lang=target_lang) -> None:
                _enqueue_translation_if_active(repo, run_id, _lang, section, text)
```

Keep the post-success backfill unchanged except optionally replacing direct `translate_section_task.apply_async(...)` with `_enqueue_translation_if_active(...)`; it already only runs when `run.status == "succeeded"`.

- [ ] **Step 4: Run translation enqueue tests**

Run:

```bash
pytest tests/worker/test_jobs.py::test_enqueue_translation_if_active_skips_cancelling_run tests/worker/test_jobs.py::test_enqueue_translation_if_active_enqueues_running_run -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/worker/jobs.py tests/worker/test_jobs.py
git commit -m "feat(worker): skip translation enqueue after cancellation"
```

## Task 7: Regression Test Suite

**Files:**
- No source changes expected.
- Test: worker, graph, API cancellation, translation, cancellation token.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest \
  tests/worker/test_cancellation.py \
  tests/worker/test_jobs.py \
  tests/graph/test_run_context.py \
  tests/api/test_runs_routes.py \
  tests/api/test_repositories.py \
  tests/test_translation.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run compile check**

Run:

```bash
python -m compileall -q tradingagents tests
```

Expected: exit code 0.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git status --short
git log --oneline --max-count=8
```

Expected: only intended commits from this plan are present; no unstaged files remain.

- [ ] **Step 4: Final commit if needed**

If Step 3 shows uncommitted verification-only changes, commit them:

```bash
git add tradingagents tests
git commit -m "test: verify cooperative run cancellation"
```

Expected: clean working tree.

## Self-Review

- Spec coverage: DB token, worker context, graph node checks, stream checks, translation enqueue blocking, cancellation final state, and no-result behavior are each covered by tasks.
- Placeholder scan: no open-ended implementation steps remain; every code step includes concrete snippets and commands.
- Type consistency: `RunContext`, `CancellationToken`, `AnalysisCancelled`, `_execute_with_optional_run_id`, `run_tradingagents_analysis`, and `_enqueue_translation_if_active` are named consistently across tasks.
