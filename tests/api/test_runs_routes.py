from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session, get_task_enqueue, get_task_revoke
from tradingagents.api.models import AnalysisRun
from tradingagents.api.repositories import AnalysisRunRepository


def _login_admin(client: TestClient) -> None:
    """Register the first user (auto-admin) and log them in.

    After this, ``client.cookies`` carries the session + csrf cookies, and
    ``client.headers`` is updated to include ``X-CSRF-Token`` so the test
    code can issue state-changing requests without restating the header.
    """
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    csrf = client.cookies.get("tradingagents_csrf")
    client.headers.update({"X-CSRF-Token": csrf})


def _put_model_settings(client: TestClient) -> None:
    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
        },
    )
    assert response.status_code == 200


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
    client = TestClient(app)
    _login_admin(client)
    _put_model_settings(client)
    return client, Session, task_ids


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
    client = TestClient(app, raise_server_exceptions=False)
    _login_admin(client)
    _put_model_settings(client)
    return client, Session


def test_post_runs_requires_model_settings():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_task_enqueue] = lambda: lambda run_id: "celery-test-id"
    client = TestClient(app)
    _login_admin(client)

    response = client.post(
        "/runs",
        json={
            "ticker": "nvda",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "model settings not configured"


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
    assert body["queue_position"] >= 1
    assert task_ids == []

    with Session() as session:
        run = AnalysisRunRepository(session).get_run(body["run_id"])
        assert run.ticker == "NVDA"
        assert run.celery_task_id is None
        assert run.llm_config == {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
            "api_key_encrypted": None,
        }


def test_create_run_only_queues_and_does_not_enqueue_celery():
    calls = []

    def enqueue(run_id: str) -> str:
        calls.append(run_id)
        return "celery-test-id"

    client, _Session = _client_with_enqueue(enqueue)

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
    assert body["queue_position"] >= 1
    assert calls == []


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


def test_get_run_returns_dispatching_status():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run.status = "dispatching"
        run_id = run.run_id
        session.commit()

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "dispatching"


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


def test_post_runs_commits_queued_run_without_enqueue():
    calls = []
    client, Session = _client_with_enqueue(calls.append)

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
    assert calls == []
    with Session() as session:
        run = session.query(AnalysisRun).one()
        assert run.status == "queued"
        assert run.celery_task_id is None
        assert body["run_id"] == run.run_id


def test_post_cancel_queued_run_marks_cancelled_and_revokes_task():
    client, Session, _ = _client()
    revoked = []
    client.app.dependency_overrides[get_task_revoke] = lambda: revoked.append

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.set_celery_task_id(run.run_id, "celery-test-id")
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"run_id": run_id, "status": "cancelled"}
    assert revoked == ["celery-test-id"]
    with Session() as session:
        saved = AnalysisRunRepository(session).get_run(run_id)
        assert saved.status == "cancelled"


def test_post_cancel_missing_run_returns_404():
    client, _Session, _ = _client()

    response = client.post("/runs/run_missing/cancel")

    assert response.status_code == 404


def test_post_cancel_succeeded_run_returns_409():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.store_success(run.run_id, "Hold", {}, {})
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 409


def test_post_cancel_requires_authentication():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.post("/runs/run_any/cancel")

    assert response.status_code == 401


def test_post_cancel_missing_csrf_returns_403():
    client, Session, _ = _client()
    client.headers.pop("X-CSRF-Token", None)
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 403
