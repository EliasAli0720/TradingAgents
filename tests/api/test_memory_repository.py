from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.memory_repository import AnalysisMemoryRepository
from tradingagents.api.repositories import AnalysisRunRepository


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisMemoryRepository(session)


def test_memory_repository_returns_same_ticker_and_cross_ticker_context():
    session, repo = _repo()
    runs = AnalysisRunRepository(session)
    nvda_run = runs.create_run("NVDA", date(2026, 1, 15), "stock", ["market"], user_id="usr_1")
    aapl_run = runs.create_run("AAPL", date(2026, 1, 16), "stock", ["market"], user_id="usr_1")
    session.flush()
    repo.store_decision(
        "usr_1",
        nvda_run.run_id,
        "NVDA",
        date(2026, 1, 15),
        "Rating: Hold",
        pending=False,
        reflection="Worked.",
    )
    repo.store_decision(
        "usr_1",
        aapl_run.run_id,
        "AAPL",
        date(2026, 1, 16),
        "Rating: Buy",
        pending=False,
        reflection="Good.",
    )
    session.commit()

    context = repo.get_past_context("usr_1", "NVDA")

    assert "Past analyses of NVDA" in context
    assert "Recent cross-ticker lessons" in context
    assert "Worked." in context
    assert "Good." in context


def test_memory_repository_resolves_pending_entry():
    session, repo = _repo()
    run = AnalysisRunRepository(session).create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
    )
    session.flush()
    entry = repo.store_decision(
        "usr_1",
        run.run_id,
        "NVDA",
        date(2026, 1, 15),
        "Rating: Hold",
    )
    session.commit()

    pending = repo.lock_pending_for_ticker("usr_1", "NVDA")
    repo.resolve_pending(
        entry.id,
        raw_return=0.05,
        alpha_return=0.02,
        holding_days=5,
        reflection="Momentum confirmed.",
    )
    session.commit()

    assert [item.id for item in pending] == [entry.id]
    saved = repo.lock_pending_for_ticker("usr_1", "NVDA")
    assert saved == []
    context = repo.get_past_context("usr_1", "NVDA")
    assert "+5.0%" in context
    assert "+2.0%" in context
    assert "Momentum confirmed." in context
