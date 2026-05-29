from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import AnalysisRun
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


def test_cancellation_token_raises_when_cancelled():
    token = CancellationToken(lambda: True)

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_cancellation_token_allows_when_not_cancelled():
    token = CancellationToken(lambda: False)

    token.raise_if_cancelled()


def test_db_cancellation_token_raises_when_run_is_cancelling():
    Session = _session_factory()
    with Session() as session:
        run = AnalysisRunRepository(session).create_run(
            "NVDA",
            date(2026, 1, 15),
            "stock",
            ["market"],
            user_id="usr_1",
        )
        run_id = run.run_id
        session.commit()

    token = build_db_cancellation_token(Session, run_id)

    with Session() as session:
        run = session.get(AnalysisRun, run_id)
        run.status = "cancelling"
        session.commit()

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_db_cancellation_token_raises_when_run_is_missing():
    Session = _session_factory()
    token = build_db_cancellation_token(Session, "missing_run")

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_db_cancellation_token_allows_when_status_check_fails(caplog):
    def broken_session_factory():
        raise RuntimeError("database unavailable")

    token = build_db_cancellation_token(broken_session_factory, "run_1")

    with caplog.at_level("WARNING"):
        token.raise_if_cancelled()

    assert "cancellation status check failed for run run_1" in caplog.text
