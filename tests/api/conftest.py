"""API-test-scoped fixtures.

The default cookie policy sets ``Secure`` on auth cookies, but FastAPI's
``TestClient`` (httpx under the hood) does not store ``Secure`` cookies sent
over the plain-HTTP test transport. Disable ``Secure`` for the duration of
api tests so login cookies actually round-trip.
"""

import pytest


@pytest.fixture(autouse=True)
def _disable_secure_cookies(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_SECURE", "false")


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    """The /auth/login limiter is a process-global singleton. Reset it
    between tests so accumulated attempts don't bleed across test cases."""
    from tradingagents.api import deps

    deps._login_limiter = None
    yield
    deps._login_limiter = None
