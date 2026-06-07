from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session, get_model_probe
from tradingagents.api.model_probe import ModelProbeResult


FERNET_KEY = "dBBj0g2y16HOVnBCwG9r20eyHmxtPXgvBXVHfJfRB4U="


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


def test_get_model_options_returns_seeded_provider_catalog():
    client = _client()
    _login(client)

    response = client.get("/settings/model/options")

    assert response.status_code == 200
    providers = {provider["id"]: provider for provider in response.json()["providers"]}
    assert providers["openai"]["required_env_var"] == "OPENAI_API_KEY"
    assert providers["openai"]["supports_custom_model"] is False
    assert providers["openai"]["backend_url_editable"] is False
    assert providers["openai"]["quick_models"][0] == {
        "id": "gpt-5.4-mini",
        "label": "GPT-5.4 Mini - Fast, strong coding and tool use",
    }
    assert providers["ollama"]["required_env_var"] is None
    assert providers["ollama"]["default_backend_url"] == "http://localhost:11434/v1"
    assert providers["ollama"]["backend_url_editable"] is True
    assert providers["ollama"]["supports_custom_model"] is True


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
        "has_api_key": False,
        "api_key_masked": None,
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


def test_put_model_settings_rejects_unknown_model_for_strict_provider():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "missing-model",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported quick_think_llm for provider openai"


def test_put_model_settings_allows_custom_model_for_custom_provider():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "qwen",
            "deep_think_llm": "qwen-next-experimental",
            "quick_think_llm": "qwen-fast-experimental",
            "backend_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["llm_provider"] == "qwen"
    assert response.json()["deep_think_llm"] == "qwen-next-experimental"
    assert response.json()["quick_think_llm"] == "qwen-fast-experimental"


def test_put_model_settings_rejects_private_backend_url_in_production(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", "false")
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "ollama",
            "deep_think_llm": "llama3.1",
            "quick_think_llm": "llama3.1",
            "backend_url": "http://127.0.0.1:11434/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert "private backend URLs are disabled" in response.json()["detail"]


def test_put_model_settings_allows_private_backend_url_when_enabled(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", "true")
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "ollama",
            "deep_think_llm": "llama3.1",
            "quick_think_llm": "llama3.1",
            "backend_url": "http://127.0.0.1:11434/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["backend_url"] == "http://127.0.0.1:11434/v1"


def test_model_settings_stores_masks_preserves_and_clears_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
            "api_key": "sk-test-abcdef123456",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert response.json()["api_key_masked"] == "sk-t...3456"
    assert "abcdef123456" not in response.text

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
    assert response.json()["has_api_key"] is True

    response = client.delete(
        "/settings/model/api-key",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 204

    response = client.get("/settings/model")
    assert response.status_code == 200
    assert response.json()["has_api_key"] is False
    assert response.json()["api_key_masked"] is None


def test_model_settings_clears_api_key_when_provider_changes(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
            "api_key": "sk-openai-abcdef123456",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["has_api_key"] is True

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "anthropic",
            "deep_think_llm": "claude-opus-4-7",
            "quick_think_llm": "claude-haiku-4-5",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["has_api_key"] is False


def test_validate_model_settings_reports_user_service_and_missing_key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _client()
    csrf = _login(client)

    client.app.dependency_overrides[get_model_probe] = lambda: (
        lambda _request: ModelProbeResult(status="success", message="probe returned pong")
    )

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

    missing = client.post(
        "/settings/model/validate",
        headers={"X-CSRF-Token": csrf},
    )
    assert missing.status_code == 200
    assert missing.json() == {
        "valid": False,
        "provider": "openai",
        "required_env_var": "OPENAI_API_KEY",
        "api_key_source": "none",
        "message": "missing API key for provider openai",
    }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-service-abcdef123456")
    service = client.post(
        "/settings/model/validate",
        headers={"X-CSRF-Token": csrf},
    )
    assert service.status_code == 200
    assert service.json()["valid"] is True
    assert service.json()["api_key_source"] == "service"

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
            "api_key": "sk-user-abcdef123456",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    user_key = client.post(
        "/settings/model/validate",
        headers={"X-CSRF-Token": csrf},
    )
    assert user_key.status_code == 200
    assert user_key.json()["valid"] is True
    assert user_key.json()["api_key_source"] == "user"


def test_validate_model_settings_runs_live_probe_with_service_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-service-abcdef123456")
    client = _client()
    csrf = _login(client)
    calls = []

    def fake_probe(request):
        calls.append(request)
        return ModelProbeResult(status="success", message="probe returned pong")

    client.app.dependency_overrides[get_model_probe] = lambda: fake_probe

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": "https://llm.example.com/v1",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    validated = client.post(
        "/settings/model/validate",
        headers={"X-CSRF-Token": csrf},
    )

    assert validated.status_code == 200
    assert validated.json() == {
        "valid": True,
        "provider": "openai",
        "required_env_var": "OPENAI_API_KEY",
        "api_key_source": "service",
        "message": "service API key configured in OPENAI_API_KEY",
        "probe_status": "success",
        "probe_message": "probe returned pong",
    }
    assert len(calls) == 1
    assert calls[0].provider == "openai"
    assert calls[0].model == "gpt-5.4-mini"
    assert calls[0].backend_url == "https://llm.example.com/v1"
    assert calls[0].api_key == "sk-service-abcdef123456"


def test_validate_model_settings_live_probe_failure_marks_config_invalid(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _client()
    csrf = _login(client)

    def fake_probe(_request):
        return ModelProbeResult(
            status="model_not_found",
            message="model was not found by provider",
        )

    client.app.dependency_overrides[get_model_probe] = lambda: fake_probe

    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "qwen",
            "deep_think_llm": "qwen3.6-plus",
            "quick_think_llm": "missing-model",
            "backend_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-user-abcdef123456",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    validated = client.post(
        "/settings/model/validate",
        headers={"X-CSRF-Token": csrf},
    )

    assert validated.status_code == 200
    assert validated.json()["valid"] is False
    assert validated.json()["api_key_source"] == "user"
    assert validated.json()["probe_status"] == "model_not_found"
    assert validated.json()["probe_message"] == "model was not found by provider"


def test_login_and_me_include_language_default_zh():
    client = _client()
    reg = client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    assert reg.json()["language"] == "zh"
    login = client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    assert login.json()["language"] == "zh"
    assert client.get("/auth/me").json()["language"] == "zh"


def test_put_preferences_persists_language():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/preferences",
        json={"language": "en"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 204
    assert client.get("/auth/me").json()["language"] == "en"


def test_put_preferences_rejects_unknown_language():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/settings/preferences",
        json={"language": "fr"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_put_preferences_requires_authentication():
    client = _client()
    response = client.put("/settings/preferences", json={"language": "en"})
    assert response.status_code in (401, 403)


def test_translation_options_lists_three_models():
    client = _client()
    _login(client)
    resp = client.get("/settings/translation/options")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    models = {(p["id"], p["model_id"]) for p in providers}
    assert ("openai", "gpt-4o-mini") in models
    assert ("deepseek", "deepseek-v4-flash") in models
    assert ("google", "gemini-2.5-flash-lite") in models


def test_translation_settings_crud_and_validation():
    client = _client()
    csrf = _login(client)

    # Not configured yet
    assert client.get("/settings/translation").status_code == 404

    # Save a valid combo
    r = client.put(
        "/settings/translation",
        json={
            "llm_provider": "deepseek",
            "model": "deepseek-v4-flash",
            "backend_url": "https://api.deepseek.com",
            "api_key": "sk-translate-123456",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["llm_provider"] == "deepseek"
    assert body["model"] == "deepseek-v4-flash"
    assert body["has_api_key"] is True
    assert body["api_key_masked"] and "sk-translate-123456" not in body["api_key_masked"]

    # Changing provider without a replacement key clears the old provider key.
    changed = client.put(
        "/settings/translation",
        json={
            "llm_provider": "openai",
            "model": "gpt-4o-mini",
            "backend_url": None,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["has_api_key"] is False

    # Invalid provider/model combo is rejected
    bad = client.put(
        "/settings/translation",
        json={"llm_provider": "openai", "model": "deepseek-v4-flash"},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 422

    # Clear key
    cleared = client.delete("/settings/translation/api-key", headers={"X-CSRF-Token": csrf})
    assert cleared.status_code == 204
    assert client.get("/settings/translation").json()["has_api_key"] is False
