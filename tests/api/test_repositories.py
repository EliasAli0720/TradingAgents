from datetime import date, datetime, timezone
from threading import Thread

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
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
