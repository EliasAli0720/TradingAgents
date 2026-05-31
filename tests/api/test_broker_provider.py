"""Tests for broker_provider: per-user broker selection + token refresh."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api import broker_provider
from tradingagents.api.broker_credential_repository import (
    BrokerCredentialRepository,
)
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import User
from tradingbot.broker.webull import WebullBroker
from tradingbot.broker.webull_oauth import TokenResponse, WebullOAuthError

pytestmark = pytest.mark.unit


@pytest.fixture()
def Session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _user(role="admin"):
    return User(user_id="u1", username="u1", password_hash="x", role=role, is_active=True)


class FakeOAuth:
    def __init__(self, token=None, fail=False):
        self.token = token or TokenResponse(
            access_token="fresh", refresh_token="newref", expires_in=1800,
            refresh_expires_in=1296000,
        )
        self.fail = fail
        self.refresh_calls = 0

    def refresh(self, refresh_token):
        self.refresh_calls += 1
        if self.fail:
            raise WebullOAuthError("nope")
        return self.token


class FakeConnService:
    def build_broker(self):
        return "ibkr-broker"


def _seed_webull(s, *, expires_in=1800, refresh_token="r"):
    repo = BrokerCredentialRepository(s, "u1")
    repo.upsert(access_token="a", refresh_token=refresh_token,
                expires_in=expires_in, account_id="DU1")
    s.commit()
    return repo


# --------------------------------------------------------------------------- #
# resolve_active_broker                                                        #
# --------------------------------------------------------------------------- #


def test_resolve_defaults_to_ibkr_without_credential(Session):
    with Session() as s:
        assert broker_provider.resolve_active_broker(s, _user(), {"broker": "ibkr"}) == "ibkr"


def test_resolve_picks_webull_when_connected(Session):
    with Session() as s:
        _seed_webull(s)
        assert broker_provider.resolve_active_broker(s, _user(), {"broker": "ibkr"}) == "webull"


def test_resolve_ignores_expired_credential(Session):
    with Session() as s:
        repo = _seed_webull(s)
        repo.mark_expired()
        s.commit()
        assert broker_provider.resolve_active_broker(s, _user(), {"broker": "ibkr"}) == "ibkr"


# --------------------------------------------------------------------------- #
# ensure_fresh_token                                                          #
# --------------------------------------------------------------------------- #


def test_fresh_token_returned_without_refresh(Session):
    with Session() as s:
        repo = _seed_webull(s, expires_in=1800)
        cred = repo.require()
        oauth = FakeOAuth()
        token = broker_provider.ensure_fresh_token(cred, repo, oauth)
        assert token == "a"
        assert oauth.refresh_calls == 0


def test_near_expiry_triggers_refresh_and_persists(Session):
    with Session() as s:
        repo = _seed_webull(s, expires_in=10)  # within leeway → refresh
        cred = repo.require()
        oauth = FakeOAuth()
        token = broker_provider.ensure_fresh_token(cred, repo, oauth)
        s.commit()
        assert token == "fresh"
        assert oauth.refresh_calls == 1
        # New tokens persisted (rolling refresh).
        assert repo.access_token(repo.require()) == "fresh"
        assert repo.refresh_token(repo.require()) == "newref"


def test_expired_without_refresh_token_raises_and_marks_expired(Session):
    with Session() as s:
        repo = _seed_webull(s, expires_in=10, refresh_token=None)
        cred = repo.require()
        with pytest.raises(PermissionError):
            broker_provider.ensure_fresh_token(cred, repo, FakeOAuth())
        s.commit()
        assert repo.require().status == "expired"


def test_refresh_failure_marks_expired(Session):
    with Session() as s:
        repo = _seed_webull(s, expires_in=10)
        cred = repo.require()
        with pytest.raises(PermissionError):
            broker_provider.ensure_fresh_token(cred, repo, FakeOAuth(fail=True))
        s.commit()
        assert repo.require().status == "expired"


# --------------------------------------------------------------------------- #
# build_user_broker                                                           #
# --------------------------------------------------------------------------- #


def test_build_user_broker_returns_ibkr_without_credential(Session):
    with Session() as s:
        broker = broker_provider.build_user_broker(
            s, _user(), {"broker": "ibkr"}, FakeConnService()
        )
        assert broker == "ibkr-broker"


def test_build_user_broker_returns_webull_with_credential(Session):
    with Session() as s:
        _seed_webull(s, expires_in=1800)
        broker = broker_provider.build_user_broker(
            s, _user(), {"broker": "ibkr", "paper_trading": True}, FakeConnService(),
            oauth_client=FakeOAuth(),
        )
        assert isinstance(broker, WebullBroker)
        assert broker._account_id == "DU1"


# --------------------------------------------------------------------------- #
# status_for                                                                  #
# --------------------------------------------------------------------------- #


class FakeBrokerRepo:
    pass


def test_status_for_falls_back_to_ibkr_status(Session):
    captured = {}

    class Svc:
        def status(self, repo):
            captured["called"] = True
            return {"broker": "ibkr", "connected": False, "gateway_online": False,
                    "brokerage_session": False, "account_id": None, "paper": True,
                    "last_refresh_at": None, "last_error": "connector not running"}

    with Session() as s:
        out = broker_provider.status_for(s, _user(), {}, Svc(), FakeBrokerRepo())
        assert captured.get("called")
        assert out["broker"] == "ibkr"


def test_status_for_reports_webull_connected(Session):
    with Session() as s:
        _seed_webull(s, expires_in=1800)
        out = broker_provider.status_for(s, _user(), {"paper_trading": True}, None, None)
        assert out["broker"] == "webull"
        assert out["connected"] is True
        assert out["account_id"] == "DU1"
