from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session, get_stream_session_factory
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.routers import runs as runs_router


def test_events_stream_emits_historical_events_in_order():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_stream_session_factory] = lambda: Session

    client = TestClient(app)
    # Register first user → auto-admin so SSE handshake can see __system__ runs.
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        repo.mark_running(run_id)
        repo.store_success(
            run_id,
            "Hold",
            {"final_trade_decision": "Rating: Hold"},
            {"ticker": "NVDA"},
        )
        session.commit()

    with client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: run_queued" in text
    assert "event: run_started" in text
    assert "event: run_succeeded" in text
    assert text.index("run_queued") < text.index("run_started") < text.index("run_succeeded")


def test_events_stream_closes_after_cancelled_event(monkeypatch):
    async def fail_sleep(_seconds):
        raise AssertionError("SSE stream did not close after run_cancelled")

    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_stream_session_factory] = lambda: Session

    client = TestClient(app)
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        repo.cancel_run(run_id, "user requested cancellation")
        session.commit()

    monkeypatch.setattr(runs_router.asyncio, "sleep", fail_sleep)

    with client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: run_queued" in text
    assert "event: run_cancelled" in text
    assert text.index("run_queued") < text.index("run_cancelled")
