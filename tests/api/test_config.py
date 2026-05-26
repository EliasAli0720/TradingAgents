import pytest

from tradingagents.api.config import get_api_settings


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_api_settings()
