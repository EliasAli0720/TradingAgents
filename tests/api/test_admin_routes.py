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
    client.post("/auth/login", json={"username": username, "password": password})
    csrf = client.cookies.get("tradingagents_csrf")
    client.headers.update({"X-CSRF-Token": csrf})


def test_admin_list_users():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")  # admin
    other = TestClient(app)
    _register_login(other, "bob")  # viewer

    r = admin.get("/admin/users")
    assert r.status_code == 200
    usernames = sorted(u["username"] for u in r.json())
    assert usernames == ["alice", "bob"]
    alice_row = next(u for u in r.json() if u["username"] == "alice")
    assert alice_row["role"] == "admin"


def test_non_admin_cannot_list_users():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")
    viewer = TestClient(app)
    _register_login(viewer, "bob")
    r = viewer.get("/admin/users")
    assert r.status_code == 403


def test_admin_patch_user_role_and_active():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")
    viewer = TestClient(app)
    _register_login(viewer, "bob")

    # Look up bob's user_id.
    users = admin.get("/admin/users").json()
    bob_id = next(u["user_id"] for u in users if u["username"] == "bob")

    r = admin.patch(f"/admin/users/{bob_id}", json={"role": "operator"})
    assert r.status_code == 200
    assert r.json()["role"] == "operator"

    r = admin.patch(f"/admin/users/{bob_id}", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_admin_revoke_all_sessions_kicks_user():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")
    viewer = TestClient(app)
    _register_login(viewer, "bob")
    assert viewer.get("/auth/me").status_code == 200

    users = admin.get("/admin/users").json()
    bob_id = next(u["user_id"] for u in users if u["username"] == "bob")

    r = admin.post(f"/admin/users/{bob_id}/sessions:revoke-all")
    assert r.status_code == 204
    assert viewer.get("/auth/me").status_code == 401


def test_admin_list_runs_across_users():
    app, _ = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")
    admin.post(
        "/runs",
        json={
            "ticker": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "analysts": ["market"],
        },
    )
    r = admin.get("/admin/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    assert runs[0]["ticker"] == "NVDA"
