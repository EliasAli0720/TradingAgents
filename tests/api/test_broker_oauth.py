"""API tests for the Webull OAuth router (/broker/oauth/webull)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api import deps
from tradingagents.api.app import create_app
from tradingagents.api.broker_credential_repository import BrokerCredentialRepository
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session
from tradingagents.api.routers import broker_oauth
from tradingbot.broker.webull_oauth import TokenResponse, WebullOAuthError

pytestmark = pytest.mark.unit


class FakeOAuthClient:
    class _Cfg:
        scope = "trade account"

    def __init__(self):
        self.config = self._Cfg()
        self.exchanged = []
        self.fail_exchange = False

    def authorize_url(self, state):
        return f"https://webull.test/authorize?state={state}"

    def exchange_code(self, code):
        self.exchanged.append(code)
        if self.fail_exchange:
            raise WebullOAuthError("bad code")
        return TokenResponse(
            access_token="acc", refresh_token="ref", expires_in=1800,
            refresh_expires_in=1296000, account_id="DU555", scope="trade account",
        )

    def refresh(self, refresh_token):
        return TokenResponse(
            access_token="acc2", refresh_token="ref2", expires_in=1800,
            refresh_expires_in=1296000,
        )


def _make_app():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    fake_oauth = FakeOAuthClient()
    resolver_calls = []

    def fake_api_key_account_resolver(app_key, app_secret, region, paper, endpoint):
        resolver_calls.append(
            {
                "app_key": app_key,
                "app_secret": app_secret,
                "region": region,
                "paper": paper,
                "endpoint": endpoint,
            }
        )
        return ["DU777"]

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[deps.get_redis_client] = lambda: None
    app.dependency_overrides[broker_oauth.get_oauth_client] = lambda: fake_oauth
    app.dependency_overrides[broker_oauth.get_api_key_account_resolver] = (
        lambda: fake_api_key_account_resolver
    )
    app.state.webull_api_key_resolver_calls = resolver_calls
    return app, Session, fake_oauth


def _login(client, username="alice", password="hunter22a"):
    client.post("/auth/register", json={"username": username, "password": password})
    client.post("/auth/login", json={"username": username, "password": password})
    client.headers.update({"X-CSRF-Token": client.cookies.get("tradingagents_csrf")})


def _client():
    app, Session, fake = _make_app()
    client = TestClient(app)
    _login(client)
    return client, Session, fake


# --------------------------------------------------------------------------- #
# authorize / status                                                          #
# --------------------------------------------------------------------------- #


def test_authorize_requires_auth():
    app, _, _ = _make_app()
    assert TestClient(app).get("/broker/oauth/webull/authorize").status_code == 401


def test_authorize_returns_url_with_state():
    client, _, _ = _client()
    body = client.get("/broker/oauth/webull/authorize").json()
    assert body["authorize_url"].startswith("https://webull.test/authorize?state=")
    assert "state=" in body["authorize_url"]


def test_status_not_connected_initially():
    client, _, _ = _client()
    body = client.get("/broker/oauth/webull/status").json()
    assert body["connected"] is False
    assert body["status"] == "not_connected"


def test_api_key_connect_validates_and_stores_credential():
    client, Session, _ = _client()
    resp = client.post(
        "/broker/oauth/webull/api-key",
        json={"app_key": "key-1", "app_secret": "secret-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["status"] == "connected"
    assert body["auth_type"] == "api_key"
    assert body["account_id"] == "DU777"

    calls = client.app.state.webull_api_key_resolver_calls
    assert calls == [
        {
            "app_key": "key-1",
            "app_secret": "secret-1",
            "region": "us",
            "paper": True,
            "endpoint": "",
        }
    ]
    with Session() as s:
        from tradingagents.api.models import User

        user_id = s.query(User).filter_by(username="alice").one().user_id
        cred = BrokerCredentialRepository(s, user_id).require()
        assert cred.auth_type == "api_key"
        assert BrokerCredentialRepository(s, user_id).app_key(cred) == "key-1"
        assert BrokerCredentialRepository(s, user_id).app_secret(cred) == "secret-1"


def test_api_key_connect_requires_account_when_multiple_accounts_found():
    client, _, _ = _client()

    def resolver(*_args):
        return ["DU1", "DU2"]

    client.app.dependency_overrides[broker_oauth.get_api_key_account_resolver] = (
        lambda: resolver
    )
    resp = client.post(
        "/broker/oauth/webull/api-key",
        json={"app_key": "key-1", "app_secret": "secret-1"},
    )
    assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# callback                                                                    #
# --------------------------------------------------------------------------- #


def _state_for(client):
    url = client.get("/broker/oauth/webull/authorize").json()["authorize_url"]
    return url.split("state=", 1)[1]


def test_callback_exchanges_and_stores(client_factory=None):
    client, Session, fake = _client()
    state = _state_for(client)
    resp = client.get(
        "/broker/oauth/webull/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "connected=webull" in resp.headers["location"]
    assert fake.exchanged == ["abc"]

    status = client.get("/broker/oauth/webull/status").json()
    assert status["connected"] is True
    assert status["account_id"] == "DU555"


def test_callback_rejects_bad_state():
    client, _, _ = _client()
    resp = client.get(
        "/broker/oauth/webull/callback",
        params={"code": "abc", "state": "garbage"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_callback_redirects_with_error_on_exchange_failure():
    client, _, fake = _client()
    fake.fail_exchange = True
    state = _state_for(client)
    resp = client.get(
        "/broker/oauth/webull/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=" in resp.headers["location"]


def test_callback_state_binds_to_issuing_user():
    """A state minted for alice must attach the credential to alice, even when
    a different user's browser hits the callback."""
    from tradingagents.api.models import BrokerCredential, User

    client, Session, _ = _client()
    state = _state_for(client)  # alice's state

    with Session() as s:
        alice_id = s.query(User).filter_by(username="alice").one().user_id

    bob = TestClient(client.app)
    _login(bob, "bob", "hunter22b")
    bob.get(
        "/broker/oauth/webull/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )

    with Session() as s:
        creds = s.query(BrokerCredential).all()
        assert len(creds) == 1
        assert creds[0].user_id == alice_id  # bound to the state owner, not bob
        assert creds[0].status == "connected"


# --------------------------------------------------------------------------- #
# refresh / disconnect                                                        #
# --------------------------------------------------------------------------- #


def test_refresh_without_credential_404():
    client, _, _ = _client()
    assert client.post("/broker/oauth/webull/refresh").status_code == 404


def test_refresh_rotates_token():
    client, Session, _ = _client()
    state = _state_for(client)
    client.get("/broker/oauth/webull/callback",
               params={"code": "abc", "state": state}, follow_redirects=False)
    resp = client.post("/broker/oauth/webull/refresh")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True


def test_disconnect_revokes():
    client, _, _ = _client()
    state = _state_for(client)
    client.get("/broker/oauth/webull/callback",
               params={"code": "abc", "state": state}, follow_redirects=False)
    resp = client.post("/broker/oauth/webull/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    assert client.get("/broker/oauth/webull/status").json()["connected"] is False
