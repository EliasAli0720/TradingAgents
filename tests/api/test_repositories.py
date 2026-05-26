from datetime import date, datetime, timezone
from threading import Thread

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import AnalysisRun, AnalysisRunEvent, AnalysisRunResult
from tradingagents.api.repositories import AnalysisRunRepository


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
    session.add(
        AnalysisRunEvent(
            run_id="run_test",
            event_type="run_queued",
            payload={"run_id": "run_test", "status": "queued"},
            created_at=now,
        )
    )
    session.add(
        AnalysisRunResult(
            run_id="run_test",
            decision="Hold",
            reports={"final_trade_decision": "Rating: Hold"},
            final_state={"company_of_interest": "NVDA"},
            created_at=now,
        )
    )
    session.commit()

    saved = session.get(AnalysisRun, "run_test")
    assert saved.ticker == "NVDA"
    assert saved.analysts == ["market", "news"]
    assert session.query(AnalysisRunEvent).one().event_type == "run_queued"
    assert session.get(AnalysisRunResult, "run_test").decision == "Hold"


def test_create_db_engine_enforces_sqlite_foreign_keys():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()

    session.add(
        AnalysisRunEvent(
            run_id="missing_run",
            event_type="run_queued",
            payload={"run_id": "missing_run", "status": "queued"},
            created_at=datetime.now(timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_create_db_engine_shares_in_memory_sqlite_across_threaded_sessions():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)

    with Session() as session:
        session.add(
            AnalysisRun(
                run_id="run_threaded",
                status="queued",
                ticker="NVDA",
                trade_date=date(2026, 1, 15),
                asset_type="stock",
                analysts=["market"],
                created_at=now,
            )
        )
        session.commit()

    result = {}

    def load_run() -> None:
        with Session() as session:
            saved = session.get(AnalysisRun, "run_threaded")
            result["ticker"] = saved.ticker if saved else None

    thread = Thread(target=load_run)
    thread.start()
    thread.join()

    assert result["ticker"] == "NVDA"


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
