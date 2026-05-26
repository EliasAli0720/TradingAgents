import pytest

from tradingagents.api.config import get_api_settings


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_api_settings()


def test_development_requires_database_url(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_api_settings()


def test_database_url_uses_postgresql_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://tradingagents:secret@postgres:5432/tradingagents",
    )

    settings = get_api_settings()

    assert (
        settings.database_url
        == "postgresql+psycopg://tradingagents:secret@postgres:5432/tradingagents"
    )


def test_auth_defaults(monkeypatch):
    for key in [
        "TRADINGAGENTS_API_SESSION_TTL_DAYS",
        "TRADINGAGENTS_API_SESSION_COOKIE_NAME",
        "TRADINGAGENTS_API_CSRF_COOKIE_NAME",
        "TRADINGAGENTS_API_COOKIE_SECURE",
        "TRADINGAGENTS_API_COOKIE_DOMAIN",
        "TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = get_api_settings()
    assert settings.session_ttl_days == 14
    assert settings.session_cookie_name == "tradingagents_session"
    assert settings.csrf_cookie_name == "tradingagents_csrf"
    assert settings.cookie_secure is True
    assert settings.cookie_domain is None
    assert settings.login_rate_limit_per_min == 5


def test_auth_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_SESSION_TTL_DAYS", "7")
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_SECURE", "false")
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_DOMAIN", "example.test")
    monkeypatch.setenv("TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN", "12")
    monkeypatch.setenv("TRADINGAGENTS_API_SESSION_COOKIE_NAME", "ta_sess")
    monkeypatch.setenv("TRADINGAGENTS_API_CSRF_COOKIE_NAME", "ta_csrf")

    settings = get_api_settings()
    assert settings.session_ttl_days == 7
    assert settings.cookie_secure is False
    assert settings.cookie_domain == "example.test"
    assert settings.login_rate_limit_per_min == 12
    assert settings.session_cookie_name == "ta_sess"
    assert settings.csrf_cookie_name == "ta_csrf"
