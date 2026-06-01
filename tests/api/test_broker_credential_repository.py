"""Tests for BrokerCredentialRepository: encryption, scoping, lifecycle."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api.broker_credential_repository import (
    CONNECTED,
    EXPIRED,
    REVOKED,
    BrokerCredentialRepository,
)
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import BrokerCredential

pytestmark = pytest.mark.unit


@pytest.fixture()
def Session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_upsert_then_get_round_trips_tokens(Session):
    with Session() as s:
        repo = BrokerCredentialRepository(s, "user-1")
        repo.upsert(
            access_token="acc-tok",
            refresh_token="ref-tok",
            expires_in=1800,
            refresh_expires_in=1296000,
            account_id="DU100",
            scope="trade account",
        )
        s.commit()
        cred = repo.require()
        assert cred.account_id == "DU100"
        assert cred.status == CONNECTED
        assert repo.access_token(cred) == "acc-tok"
        assert repo.refresh_token(cred) == "ref-tok"
        # Stored encrypted, not plaintext.
        assert cred.access_token_enc != "acc-tok"
        assert cred.token_expires_at is not None
        assert cred.refresh_expires_at is not None


def test_upsert_api_key_round_trips_encrypted_secrets(Session):
    with Session() as s:
        repo = BrokerCredentialRepository(s, "user-1")
        repo.upsert_api_key(
            app_key="app-key-123",
            app_secret="app-secret-456",
            account_id="DU200",
            region="us",
        )
        s.commit()

        cred = repo.require()
        assert cred.auth_type == "api_key"
        assert cred.account_id == "DU200"
        assert cred.status == CONNECTED
        assert cred.token_expires_at is None
        assert repo.app_key(cred) == "app-key-123"
        assert repo.app_secret(cred) == "app-secret-456"
        assert cred.app_key_enc != "app-key-123"
        assert cred.app_secret_enc != "app-secret-456"


def test_upsert_is_idempotent_per_user_broker(Session):
    with Session() as s:
        repo = BrokerCredentialRepository(s, "user-1")
        repo.upsert(access_token="a1", refresh_token="r1", expires_in=1800)
        s.commit()
        repo.upsert(access_token="a2", refresh_token="r2", expires_in=1800, account_id="DU9")
        s.commit()
        rows = s.query(BrokerCredential).filter_by(user_id="user-1").all()
        assert len(rows) == 1
        assert repo.access_token(rows[0]) == "a2"
        assert rows[0].account_id == "DU9"


def test_users_are_isolated(Session):
    with Session() as s:
        BrokerCredentialRepository(s, "user-1").upsert(
            access_token="a", refresh_token="r", expires_in=1800
        )
        BrokerCredentialRepository(s, "user-2").upsert(
            access_token="b", refresh_token="r", expires_in=1800
        )
        s.commit()
        assert BrokerCredentialRepository(s, "user-1").get() is not None
        assert BrokerCredentialRepository(s, "user-3").get() is None
        c1 = BrokerCredentialRepository(s, "user-1").require()
        assert BrokerCredentialRepository(s, "user-1").access_token(c1) == "a"


def test_update_tokens_keeps_old_refresh_when_absent(Session):
    with Session() as s:
        repo = BrokerCredentialRepository(s, "u")
        repo.upsert(access_token="a1", refresh_token="r1", expires_in=1800)
        s.commit()
        cred = repo.require()
        repo.update_tokens(cred, access_token="a2", refresh_token=None, expires_in=1800)
        s.commit()
        assert repo.access_token(cred) == "a2"
        assert repo.refresh_token(cred) == "r1"  # unchanged


def test_mark_expired_and_revoke(Session):
    with Session() as s:
        repo = BrokerCredentialRepository(s, "u")
        repo.upsert(access_token="a", refresh_token="r", expires_in=1800)
        s.commit()
        repo.mark_expired()
        s.commit()
        assert repo.require().status == EXPIRED

        repo.revoke()
        s.commit()
        cred = repo.require()
        assert cred.status == REVOKED
        assert cred.refresh_token_enc is None
        assert cred.token_expires_at is None


def test_require_raises_when_missing(Session):
    with Session() as s:
        with pytest.raises(LookupError):
            BrokerCredentialRepository(s, "nobody").require()
