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


def test_concurrency_capacity_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RUNNING_SYSTEM", "100")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RUNNING_PER_USER", "5")
    monkeypatch.setenv("TRADINGAGENTS_MAX_QUEUED_PER_USER", "50")
    monkeypatch.setenv("TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("TRADINGAGENTS_RUN_LEASE_SECONDS", "600")
    monkeypatch.setenv("TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS", "10")
    monkeypatch.setenv("TRADINGAGENTS_WORKER_STALE_AFTER_SECONDS", "90")

    settings = get_api_settings()

    assert settings.max_running_system == 100
    assert settings.max_running_per_user == 5
    assert settings.max_queued_per_user == 50
    assert settings.dispatch_interval_seconds == 1
    assert settings.run_lease_seconds == 600
    assert settings.worker_heartbeat_seconds == 10
    assert settings.worker_stale_after_seconds == 90


def test_auth_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "production")
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


def test_cookie_secure_defaults_false_for_development(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.delenv("TRADINGAGENTS_API_COOKIE_SECURE", raising=False)

    settings = get_api_settings()

    assert settings.cookie_secure is False


def test_cookie_secure_explicit_env_overrides_development(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "development")
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_SECURE", "true")

    settings = get_api_settings()

    assert settings.cookie_secure is True


def test_private_backend_urls_default_to_disabled_in_production(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "production")
    monkeypatch.delenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", raising=False)

    settings = get_api_settings()

    assert settings.allow_private_backend_urls is False


def test_private_backend_urls_default_to_enabled_in_test(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "test")
    monkeypatch.delenv("TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS", raising=False)

    settings = get_api_settings()

    assert settings.allow_private_backend_urls is True
