from pathlib import Path

from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def test_api_config_uses_safe_defaults(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_API_TOKEN", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_REDIS_URL", raising=False)
    monkeypatch.delenv("TRADINGBOT_DB_PATH", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESULTS_DIR", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_API_CORS_ORIGINS", raising=False)

    config = ApiConfig.from_env()

    assert config.redis_url == "redis://localhost:6379/0"
    assert config.db_path == str(Path.home() / ".tradingagents" / "tradingbot.db")
    assert config.results_dir == str(Path.home() / ".tradingagents" / "logs")
    assert config.cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert config.api_token is None
    assert config.auth_enabled is False


def test_api_config_redacts_secret_values(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_TOKEN", "secret-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-value")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    config = ApiConfig.from_env()
    status = config.provider_key_status(["OPENAI_API_KEY", "GOOGLE_API_KEY"])

    assert config.auth_enabled is True
    assert status == {
        "OPENAI_API_KEY": {"configured": True},
        "GOOGLE_API_KEY": {"configured": False},
    }
    assert "sk-real-value" not in str(status)


def test_settings_reports_key_status_without_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    client = TestClient(create_app(config))

    response = client.get("/api/settings", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider_keys"]["OPENAI_API_KEY"]["configured"] is True
    assert "sk-secret" not in str(body)
