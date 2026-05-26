from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session


def _client():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    return client


def _login(client: TestClient) -> str:
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    response = client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    assert response.status_code == 200
    return client.cookies.get("tradingagents_csrf")


def test_get_model_settings_requires_authentication():
    client = _client()

    response = client.get("/settings/model")

    assert response.status_code == 401


def test_get_model_settings_returns_404_until_configured():
    client = _client()
    _login(client)

    response = client.get("/settings/model")

    assert response.status_code == 404


def test_put_then_get_model_settings_for_current_user():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["llm_provider"] == "openai"

    saved = client.get("/settings/model")
    assert saved.status_code == 200
    assert saved.json() == {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.4",
        "quick_think_llm": "gpt-5.4-mini",
        "backend_url": None,
    }


def test_put_model_settings_rejects_unsupported_provider():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "made-up",
            "deep_think_llm": "x",
            "quick_think_llm": "y",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422


def test_put_model_settings_rejects_invalid_backend_url():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": "ftp://llm.example.com",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
