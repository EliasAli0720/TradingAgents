from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.dispatcher import DispatchConfig, dispatch_once
from tradingagents.worker.jobs import execute_analysis_run


def _session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _create_runs(repo: AnalysisRunRepository, user_id: str, count: int):
    return [
        repo.create_run(
            ticker="NVDA",
            trade_date=date(2026, 1, 15),
            asset_type="stock",
            analysts=["market"],
            user_id=user_id,
        )
        for _ in range(count)
    ]


def _recording_enqueue(enqueued: list[str]):
    def enqueue(run_id: str) -> str:
        enqueued.append(run_id)
        return f"task-{run_id}"

    return enqueue


def test_dispatcher_starts_at_most_five_runs_for_one_user():
    session = _session()
    repo = AnalysisRunRepository(session)
    _create_runs(repo, "usr_1", 8)
    session.commit()
    enqueued = []

    dispatched = dispatch_once(
        session,
        _recording_enqueue(enqueued),
        DispatchConfig(system_running=100, user_running=5, lease_seconds=600),
    )

    assert dispatched == 5
    assert len(enqueued) == 5
    runs = repo.list_runs_for_user("usr_1")
    assert [run.status for run in runs].count("dispatching") == 5
    assert [run.status for run in runs].count("queued") == 3


def test_dispatcher_fairly_dispatches_across_users():
    session = _session()
    repo = AnalysisRunRepository(session)
    _create_runs(repo, "usr_a", 10)
    _create_runs(repo, "usr_b", 1)
    session.commit()
    enqueued = []

    dispatch_once(
        session,
        _recording_enqueue(enqueued),
        DispatchConfig(system_running=2, user_running=5, lease_seconds=600),
    )

    enqueued_users = [repo.get_run(run_id).user_id for run_id in enqueued]
    assert enqueued_users == ["usr_a", "usr_b"]


def test_dispatcher_counts_existing_dispatching_and_running_capacity():
    session = _session()
    repo = AnalysisRunRepository(session)
    usr_1_runs = _create_runs(repo, "usr_1", 4)
    usr_1_runs[0].status = "dispatching"
    usr_1_runs[1].status = "running"
    _create_runs(repo, "usr_2", 2)
    session.commit()
    enqueued = []

    dispatched = dispatch_once(
        session,
        _recording_enqueue(enqueued),
        DispatchConfig(system_running=4, user_running=2, lease_seconds=600),
    )

    assert dispatched == 2
    assert [repo.get_run(run_id).user_id for run_id in enqueued] == ["usr_2", "usr_2"]
    assert [run.status for run in repo.list_runs_for_user("usr_1")].count("queued") == 2


def test_dispatcher_records_task_id_lease_and_dispatch_event():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = _create_runs(repo, "usr_1", 1)[0]
    session.commit()

    dispatched = dispatch_once(
        session,
        lambda run_id: f"task-{run_id}",
        DispatchConfig(system_running=1, user_running=1, lease_seconds=600),
    )

    saved = repo.get_run(run.run_id)
    event_types = [event.event_type for event in repo.list_events(run.run_id)]
    assert dispatched == 1
    assert saved.status == "dispatching"
    assert saved.celery_task_id == f"task-{run.run_id}"
    assert saved.dispatched_at is not None
    assert saved.lease_expires_at is not None
    assert event_types == ["run_queued", "run_dispatching"]


def test_dispatched_run_can_still_be_executed_before_worker_claims_dispatching_directly():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_1",
        llm_config={"llm_provider": "openai"},
    )
    session.commit()
    calls = []

    dispatch_once(
        session,
        lambda run_id: f"task-{run_id}",
        DispatchConfig(system_running=1, user_running=1, lease_seconds=600),
    )

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        calls.append((ticker, trade_date, asset_type, analysts, llm_config))
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    assert repo.get_run(run.run_id).status == "succeeded"
    assert calls == [
        (
            "NVDA",
            date(2026, 1, 15),
            "stock",
            ["market"],
            {"llm_provider": "openai"},
        )
    ]


def test_dispatcher_keeps_scanning_past_saturated_users():
    session = _session()
    repo = AnalysisRunRepository(session)
    saturated_a = _create_runs(repo, "usr_a", 2)
    saturated_a[0].status = "running"
    saturated_b = _create_runs(repo, "usr_b", 2)
    saturated_b[0].status = "running"
    _create_runs(repo, "usr_c", 1)
    session.commit()
    enqueued = []

    dispatched = dispatch_once(
        session,
        _recording_enqueue(enqueued),
        DispatchConfig(system_running=3, user_running=1, lease_seconds=600),
    )

    assert dispatched == 1
    assert [repo.get_run(run_id).user_id for run_id in enqueued] == ["usr_c"]


def test_dispatcher_rejects_missing_task_id_without_stranding_run():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = _create_runs(repo, "usr_1", 1)[0]
    session.commit()

    with pytest.raises(RuntimeError, match="task id"):
        dispatch_once(
            session,
            lambda run_id: None,
            DispatchConfig(system_running=1, user_running=1, lease_seconds=600),
        )

    saved = repo.get_run(run.run_id)
    assert saved.status == "queued"
    assert saved.celery_task_id is None
    assert saved.dispatched_at is None
    assert saved.lease_expires_at is None
    # The dispatching status is committed before enqueue (to avoid the
    # worker-runs-before-commit race), so a failed enqueue leaves a visible
    # dispatching→requeued trail rather than a silent rollback.
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_dispatching",
        "run_requeued",
    ]
