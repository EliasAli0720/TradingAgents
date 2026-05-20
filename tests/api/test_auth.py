from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def make_client(tmp_path, token="test-token"):
    config = ApiConfig(
        api_token=token,
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(config))


def test_login_rejects_invalid_token(tmp_path):
    client = make_client(tmp_path)

    response = client.post("/api/auth/login", json={"token": "wrong"})

    assert response.status_code == 401


def test_login_accepts_valid_token_and_me_requires_bearer(tmp_path):
    client = make_client(tmp_path)

    login = client.post("/api/auth/login", json={"token": "test-token"})
    assert login.status_code == 200
    assert login.json()["access_token"] == "test-token"

    denied = client.get("/api/auth/me")
    assert denied.status_code == 401

    allowed = client.get("/api/auth/me", headers={"Authorization": "Bearer test-token"})
    assert allowed.status_code == 200
    assert allowed.json()["authenticated"] is True


def test_health_endpoint_is_public_and_app_keeps_config(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    app = create_app(config)
    client = TestClient(app)

    response = client.get("/api/health")

    assert app.state.api_config is config
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
