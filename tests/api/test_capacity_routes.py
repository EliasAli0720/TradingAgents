from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session


def _build_app():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    return app, Session


def _register_login(client, username, password="hunter22a"):
    client.post("/auth/register", json={"username": username, "password": password})
    client.post("/auth/login", json={"username": username, "password": password})
    csrf = client.cookies.get("tradingagents_csrf")
    client.headers.update({"X-CSRF-Token": csrf})


def test_admin_capacity_endpoint_returns_counts():
    app, _Session = _build_app()
    admin = TestClient(app)
    _register_login(admin, "alice")

    response = admin.get("/admin/capacity")

    assert response.status_code == 200
    body = response.json()
    assert "max_running_system" in body
    assert "running_system" in body
    assert "queued_system" in body
