"""Per-user broker OAuth credential persistence (Webull Connect API).

Strictly scoped to one ``user_id``: every method only ever reads/writes that
user's row. Tokens are encrypted at rest with the shared Fernet helper
(:mod:`tradingagents.api.crypto`) — plaintext never touches the DB, logs, or
the API surface. Mirrors the repository convention: methods mutate the session;
the caller commits.

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md §4
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.crypto import decrypt_secret, encrypt_secret
from tradingagents.api.models import BrokerCredential

WEBULL = "webull"

OAUTH = "oauth"
API_KEY = "api_key"
CONNECTED = "connected"
EXPIRED = "expired"
REVOKED = "revoked"

_API_KEY_ACCESS_PLACEHOLDER = "__webull_api_key__"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expiry(seconds: Optional[int]) -> Optional[datetime]:
    if seconds is None:
        return None
    return _utcnow() + timedelta(seconds=int(seconds))


class BrokerCredentialRepository:
    def __init__(self, session: Session, user_id: str):
        self.session = session
        self.user_id = user_id

    def get(self, broker: str = WEBULL) -> Optional[BrokerCredential]:
        stmt = select(BrokerCredential).where(
            BrokerCredential.user_id == self.user_id,
            BrokerCredential.broker == broker,
        )
        return self.session.scalar(stmt)

    def require(self, broker: str = WEBULL) -> BrokerCredential:
        cred = self.get(broker)
        if cred is None:
            raise LookupError(f"no {broker} credential for user {self.user_id}")
        return cred

    # -- token access (decrypt on read) ----------------------------------- #

    @staticmethod
    def access_token(cred: BrokerCredential) -> str:
        return decrypt_secret(cred.access_token_enc)

    @staticmethod
    def refresh_token(cred: BrokerCredential) -> Optional[str]:
        if not cred.refresh_token_enc:
            return None
        return decrypt_secret(cred.refresh_token_enc)

    @staticmethod
    def app_key(cred: BrokerCredential) -> str:
        if not cred.app_key_enc:
            raise RuntimeError("Webull app key is not stored for this credential")
        return decrypt_secret(cred.app_key_enc)

    @staticmethod
    def app_secret(cred: BrokerCredential) -> str:
        if not cred.app_secret_enc:
            raise RuntimeError("Webull app secret is not stored for this credential")
        return decrypt_secret(cred.app_secret_enc)

    # -- writes ----------------------------------------------------------- #

    def upsert(
        self,
        *,
        broker: str = WEBULL,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
        refresh_expires_in: Optional[int] = None,
        account_id: Optional[str] = None,
        region: str = "us",
        scope: Optional[str] = None,
    ) -> BrokerCredential:
        cred = self.get(broker)
        now = _utcnow()
        access_enc = encrypt_secret(access_token)
        refresh_enc = encrypt_secret(refresh_token) if refresh_token else None
        if cred is None:
            cred = BrokerCredential(
                user_id=self.user_id,
                broker=broker,
                account_id=account_id,
                region=region,
                auth_type=OAUTH,
                access_token_enc=access_enc,
                refresh_token_enc=refresh_enc,
                app_key_enc=None,
                app_secret_enc=None,
                token_expires_at=_expiry(expires_in),
                refresh_expires_at=_expiry(refresh_expires_in),
                scope=scope,
                status=CONNECTED,
                created_at=now,
                updated_at=now,
            )
            self.session.add(cred)
            return cred

        cred.access_token_enc = access_enc
        if refresh_enc is not None:
            cred.refresh_token_enc = refresh_enc
            cred.refresh_expires_at = _expiry(refresh_expires_in)
        else:
            cred.refresh_token_enc = None
            cred.refresh_expires_at = None
        cred.token_expires_at = _expiry(expires_in)
        if account_id is not None:
            cred.account_id = account_id
        cred.region = region
        cred.auth_type = OAUTH
        cred.app_key_enc = None
        cred.app_secret_enc = None
        if scope is not None:
            cred.scope = scope
        cred.status = CONNECTED
        cred.updated_at = now
        return cred

    def upsert_api_key(
        self,
        *,
        broker: str = WEBULL,
        app_key: str,
        app_secret: str,
        account_id: Optional[str] = None,
        region: str = "us",
    ) -> BrokerCredential:
        """Store user-supplied Webull Trading API credentials.

        ``access_token_enc`` remains non-null for compatibility with existing
        DB rows; API-key mode reads only ``app_key_enc`` / ``app_secret_enc``.
        """
        cred = self.get(broker)
        now = _utcnow()
        app_key_enc = encrypt_secret(app_key)
        app_secret_enc = encrypt_secret(app_secret)
        access_enc = encrypt_secret(_API_KEY_ACCESS_PLACEHOLDER)
        if cred is None:
            cred = BrokerCredential(
                user_id=self.user_id,
                broker=broker,
                account_id=account_id,
                region=region,
                auth_type=API_KEY,
                access_token_enc=access_enc,
                refresh_token_enc=None,
                app_key_enc=app_key_enc,
                app_secret_enc=app_secret_enc,
                token_expires_at=None,
                refresh_expires_at=None,
                scope=None,
                status=CONNECTED,
                created_at=now,
                updated_at=now,
            )
            self.session.add(cred)
            return cred

        cred.account_id = account_id
        cred.region = region
        cred.auth_type = API_KEY
        cred.access_token_enc = access_enc
        cred.refresh_token_enc = None
        cred.app_key_enc = app_key_enc
        cred.app_secret_enc = app_secret_enc
        cred.token_expires_at = None
        cred.refresh_expires_at = None
        cred.scope = None
        cred.status = CONNECTED
        cred.updated_at = now
        return cred

    def update_tokens(
        self,
        cred: BrokerCredential,
        *,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
        refresh_expires_in: Optional[int] = None,
    ) -> BrokerCredential:
        """Write back a refreshed token pair (rolling refresh)."""
        cred.access_token_enc = encrypt_secret(access_token)
        cred.token_expires_at = _expiry(expires_in)
        if refresh_token:
            cred.refresh_token_enc = encrypt_secret(refresh_token)
            cred.refresh_expires_at = _expiry(refresh_expires_in)
        cred.status = CONNECTED
        cred.updated_at = _utcnow()
        return cred

    def mark_expired(self, broker: str = WEBULL) -> Optional[BrokerCredential]:
        cred = self.get(broker)
        if cred is not None:
            cred.status = EXPIRED
            cred.updated_at = _utcnow()
        return cred

    def revoke(self, broker: str = WEBULL) -> Optional[BrokerCredential]:
        cred = self.get(broker)
        if cred is not None:
            cred.status = REVOKED
            # Drop the secrets on revoke — keep the row for audit only.
            cred.access_token_enc = encrypt_secret("revoked")
            cred.refresh_token_enc = None
            cred.app_key_enc = None
            cred.app_secret_enc = None
            cred.token_expires_at = None
            cred.refresh_expires_at = None
            cred.updated_at = _utcnow()
        return cred
