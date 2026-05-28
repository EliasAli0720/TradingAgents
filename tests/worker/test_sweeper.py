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
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={},
    )
    run.status = "dispatching"
    run.celery_task_id = "task-expired"
    run.lease_expires_at = utcnow() - timedelta(seconds=1)
    session.commit()

    sweep_once(session, stale_after_seconds=90)

    saved = repo.get_run(run.run_id)
    assert saved.status == "queued"
    assert saved.celery_task_id is None
    assert saved.dispatched_at is None
    assert saved.lease_expires_at is None
    assert repo.list_events(run.run_id)[-1].event_type == "run_requeued"


def test_sweeper_fails_stale_running_after_attempts_exhausted():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={},
    )
    run.status = "running"
    run.attempt_count = 2
    run.max_attempts = 2
    run.heartbeat_at = utcnow() - timedelta(seconds=120)
    session.commit()

    sweep_once(session, stale_after_seconds=90)

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "worker heartbeat stale"


def test_sweeper_requeues_stale_running_when_attempts_remain():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={},
    )
    run.status = "running"
    run.attempt_count = 1
    run.max_attempts = 2
    run.heartbeat_at = utcnow() - timedelta(seconds=120)
    session.commit()

    sweep_once(session, stale_after_seconds=90)

    saved = repo.get_run(run.run_id)
    assert saved.status == "queued"
    assert saved.celery_task_id is None
    assert repo.list_events(run.run_id)[-1].event_type == "run_requeued"


def test_sweeper_keeps_recent_running_without_heartbeat():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={},
    )
    now = utcnow()
    run.status = "running"
    run.started_at = now
    run.updated_at = now
    run.heartbeat_at = None
    session.commit()

    repaired = sweep_once(session, stale_after_seconds=90)

    saved = repo.get_run(run.run_id)
    assert repaired == 0
    assert saved.status == "running"
    assert repo.list_events(run.run_id)[-1].event_type == "run_queued"
