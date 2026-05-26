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
