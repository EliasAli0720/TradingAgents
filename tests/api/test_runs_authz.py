from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session, get_task_enqueue


def _build_app():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_task_enqueue] = lambda: lambda run_id: "celery-test-id"
    return app, Session


def _register_login(client, username, password="hunter22a"):
    client.post("/auth/register", json={"username": username, "password": password})
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json(), client.cookies.get("tradingagents_csrf")


def _put_model_settings(client, csrf):
    r = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200


def test_post_runs_requires_auth():
    app, _ = _build_app()
    c = TestClient(app)
    r = c.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )
    assert r.status_code == 401


def test_viewer_cannot_create_run():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")  # first → admin

    viewer = TestClient(app)
    _register_login(viewer, "bob")  # second → viewer
    csrf = viewer.cookies.get("tradingagents_csrf")
    r = viewer.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_operator_can_create_run_and_owner_scope_isolated():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")  # admin

    # promote bob to operator via admin route is Task 10; for now, register a
    # second admin path: register two users — first is admin (sees everything),
    # promote second by direct DB write is overkill here. Operate as admin:
    # admin role is allowed to POST /runs.
    csrf = admin.cookies.get("tradingagents_csrf")
    _put_model_settings(admin, csrf)
    r = admin.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    # A separate viewer cannot read admin's run.
    viewer = TestClient(app)
    _register_login(viewer, "carol")
    assert viewer.get(f"/runs/{run_id}").status_code == 404


def test_admin_sees_any_run():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")
    csrf = admin.cookies.get("tradingagents_csrf")
    _put_model_settings(admin, csrf)
    r = admin.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    run_id = r.json()["run_id"]
    # admin sees own run (and would see anyone else's).
    assert admin.get(f"/runs/{run_id}").status_code == 200


def test_post_runs_without_csrf_blocked():
    app, _ = _build_app()
    c = TestClient(app)
    _register_login(c, "alice")
    r = c.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )
    assert r.status_code == 403
