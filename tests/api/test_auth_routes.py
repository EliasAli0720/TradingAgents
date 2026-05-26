from fastapi.testclient import TestClient
from fastapi.testclient import TestClient  # noqa: F811 — re-import for clarity
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session


def _make_client():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)
    return client


def _register(client, username="alice", password="hunter22a"):
    return client.post("/auth/register", json={"username": username, "password": password})


def _login(client, username="alice", password="hunter22a"):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_first_register_becomes_admin_subsequent_viewer():
    c = _make_client()
    r1 = _register(c, "alice", "hunter22a")
    assert r1.status_code == 201
    r2 = _register(c, "bob", "hunter22a")
    assert r2.status_code == 201

    # Confirm via login + /auth/me
    _login(c, "alice", "hunter22a")
    me = c.get("/auth/me").json()
    assert me["role"] == "admin"

    # New client for bob
    c2 = _make_client()
    _register(c2, "alice", "hunter22a")  # becomes admin in c2's db
    _register(c2, "bob", "hunter22a")
    _login(c2, "bob", "hunter22a")
    assert c2.get("/auth/me").json()["role"] == "viewer"


def test_register_rejects_weak_password():
    c = _make_client()
    r = c.post("/auth/register", json={"username": "alice", "password": "short"})
    assert r.status_code == 422


def test_register_rejects_invalid_username():
    c = _make_client()
    r = c.post("/auth/register", json={"username": "ab", "password": "hunter22a"})
    assert r.status_code == 422


def test_register_duplicate_username_409():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    r = c.post("/auth/register", json={"username": "ALICE", "password": "hunter22a"})
    assert r.status_code == 409


def test_login_sets_cookies_and_me_returns_user():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    r = _login(c, "alice", "hunter22a")
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "alice"
    assert body["role"] == "admin"
    assert c.cookies.get("tradingagents_session")
    assert c.cookies.get("tradingagents_csrf")

    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_me_without_session_returns_401():
    c = _make_client()
    r = c.get("/auth/me")
    assert r.status_code == 401


def test_login_invalid_credentials_return_identical_401():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    a = c.post("/auth/login", json={"username": "alice", "password": "WRONG222"})
    b = c.post("/auth/login", json={"username": "nobody", "password": "WRONG222"})
    assert a.status_code == 401
    assert b.status_code == 401
    assert a.json() == b.json()


def test_logout_invalidates_session():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    _login(c, "alice", "hunter22a")
    csrf = c.cookies.get("tradingagents_csrf")
    r = c.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert c.get("/auth/me").status_code == 401


def test_logout_requires_csrf():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    _login(c, "alice", "hunter22a")
    r = c.post("/auth/logout")
    assert r.status_code == 403


def test_change_password_succeeds_and_current_session_survives():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    _login(c, "alice", "hunter22a")
    csrf = c.cookies.get("tradingagents_csrf")
    r = c.post(
        "/auth/change-password",
        json={"current_password": "hunter22a", "new_password": "hunter33b"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 204
    assert c.get("/auth/me").status_code == 200


def test_change_password_wrong_current_returns_401():
    c = _make_client()
    _register(c, "alice", "hunter22a")
    _login(c, "alice", "hunter22a")
    csrf = c.cookies.get("tradingagents_csrf")
    r = c.post(
        "/auth/change-password",
        json={"current_password": "WRONG222", "new_password": "hunter33b"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 401


def test_change_password_revokes_other_sessions():
    # Two TestClients sharing the same in-memory engine via dependency override.
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override

    c1 = TestClient(app)
    c2 = TestClient(app)

    c1.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    c1.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    c2.post("/auth/login", json={"username": "alice", "password": "hunter22a"})

    # Both alive
    assert c1.get("/auth/me").status_code == 200
    assert c2.get("/auth/me").status_code == 200

    csrf = c1.cookies.get("tradingagents_csrf")
    r = c1.post(
        "/auth/change-password",
        json={"current_password": "hunter22a", "new_password": "hunter33b"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 204
    assert c1.get("/auth/me").status_code == 200
    assert c2.get("/auth/me").status_code == 401
