from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session, get_task_enqueue
from tradingagents.api.models import AnalysisRun
from tradingagents.api.repositories import AnalysisRunRepository


def _client():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    task_ids = []

    def override_session():
        with Session() as session:
            yield session

    def enqueue(run_id: str) -> str:
        task_ids.append(run_id)
        return "celery-test-id"

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_task_enqueue] = lambda: enqueue
    return TestClient(app), Session, task_ids


def _client_with_enqueue(enqueue):
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_task_enqueue] = lambda: enqueue
    return TestClient(app, raise_server_exceptions=False), Session


def test_post_runs_creates_run_and_enqueues_task():
    client, Session, task_ids = _client()
    response = client.post(
        "/runs",
        json={
            "ticker": "nvda",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_id"].startswith("run_")
    assert task_ids == [body["run_id"]]

    with Session() as session:
        run = AnalysisRunRepository(session).get_run(body["run_id"])
        assert run.ticker == "NVDA"
        assert run.celery_task_id == "celery-test-id"


def test_get_run_returns_status():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        session.commit()

    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["ticker"] == "NVDA"


def test_result_before_completion_returns_409():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        session.commit()

    response = client.get(f"/runs/{run_id}/result")
    assert response.status_code == 409


def test_result_after_completion_returns_payload():
    client, Session, _ = _client()
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

    response = client.get(f"/runs/{run_id}/result")
    assert response.status_code == 200
    assert response.json()["decision"] == "Hold"


def test_post_runs_enqueue_failure_does_not_commit_run():
    def enqueue(_run_id: str) -> str:
        raise RuntimeError("redis unavailable")

    client, Session = _client_with_enqueue(enqueue)

    response = client.post(
        "/runs",
        json={
            "ticker": "nvda",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )

    assert response.status_code == 500
    with Session() as session:
        assert session.query(AnalysisRun).count() == 0
