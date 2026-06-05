"""Per-user broker resolution for the web layer (multi-broker).

The web layer historically built one shared IBKR broker (Redis-proxied to the
single connector). With Webull (cloud REST, per-user OAuth) a user can instead
have their *own* broker. This module picks the right one per request so the
``/broker/*`` endpoints stay broker-agnostic:

  * user has a connected Webull credential → build a ``WebullBroker`` directly
    from their (auto-refreshed) access token — no Redis, no connector;
  * otherwise → the existing IBKR-over-Redis path via ``BrokerConnectionService``.

Token freshness (Webull access tokens last ~30 min) is handled here: the access
token is refreshed via the rolling refresh token immediately before building the
broker, and the new pair is written back to the credential row.

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md §5
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from tradingagents.api.broker_credential_repository import (
    API_KEY,
    CONNECTED,
    WEBULL,
    BrokerCredentialRepository,
)
from tradingagents.api.models import BrokerCredential, User

# Refresh the access token if it expires within this many seconds.
_REFRESH_LEEWAY_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_active_broker(session: Session, user: User, config: dict) -> str:
    """Which broker this user trades through right now."""
    cred = BrokerCredentialRepository(session, user.user_id).get(WEBULL)
    if cred is not None and cred.status == CONNECTED:
        return WEBULL
    return str(config.get("broker", "ibkr"))


def _needs_refresh(cred: BrokerCredential) -> bool:
    if cred.auth_type == API_KEY:
        return False
    if cred.token_expires_at is None:
        return True
    expires_at = cred.token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (expires_at - _utcnow()).total_seconds() <= _REFRESH_LEEWAY_SECONDS


def ensure_fresh_token(
    cred: BrokerCredential,
    repo: BrokerCredentialRepository,
    oauth_client,
) -> str:
    """Return a usable access token, refreshing (and persisting) if near expiry.

    Raises ``PermissionError`` when a refresh is required but impossible (no
    refresh token, or no configured OAuth client), after marking the credential
    expired — the caller surfaces this as "re-authorise Webull".
    """
    if not _needs_refresh(cred):
        return repo.access_token(cred)

    refresh_token = repo.refresh_token(cred)
    if not refresh_token or oauth_client is None:
        repo.mark_expired(cred.broker)
        raise PermissionError("Webull authorization expired; please reconnect")

    from tradingbot.broker.webull_oauth import WebullOAuthError

    try:
        token = oauth_client.refresh(refresh_token)
    except WebullOAuthError as exc:
        repo.mark_expired(cred.broker)
        raise PermissionError("Webull token refresh failed; please reconnect") from exc

    repo.update_tokens(
        cred,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_in=token.expires_in,
        refresh_expires_in=token.refresh_expires_in,
    )
    return token.access_token


def build_user_broker(
    session: Session,
    user: User,
    config: dict,
    connection_service,
    oauth_client=None,
):
    """Build the broker for *user*: Webull direct, or IBKR via the connector."""
    if resolve_active_broker(session, user, config) != WEBULL:
        return connection_service.build_broker()

    from tradingbot.broker.factory import build_broker
    from tradingbot.broker.webull_oauth import oauth_client_from_config

    repo = BrokerCredentialRepository(session, user.user_id)
    cred = repo.require(WEBULL)
    if cred.auth_type == API_KEY:
        token = ""
        app_key = repo.app_key(cred)
        app_secret = repo.app_secret(cred)
        auth_type = API_KEY
    else:
        if oauth_client is None:
            oauth_client = oauth_client_from_config(config)
        token = ensure_fresh_token(cred, repo, oauth_client)
        session.commit()  # persist a rolling refresh before we use the token
        app_key = str(config.get("webull_app_key", ""))
        app_secret = str(config.get("webull_app_secret", ""))
        auth_type = "oauth"

    cfg = dict(config)
    cfg.update(
        broker="webull",
        webull_auth_type=auth_type,
        webull_access_token=token,
        webull_app_key=app_key,
        webull_app_secret=app_secret,
        webull_account_id=cred.account_id or "",
        webull_region=cred.region,
    )
    return build_broker(cfg, mode="server")


def status_for(
    session: Session,
    user: User,
    config: dict,
    connection_service,
    broker_repo,
) -> dict:
    """Connection status for ``/broker/status``, per the user's active broker."""
    cred = BrokerCredentialRepository(session, user.user_id).get(WEBULL)
    if cred is None:
        return connection_service.status(broker_repo)

    connected = cred.status == CONNECTED and not _refresh_token_dead(cred)
    accounts = [cred.account_id] if cred.account_id else []
    return {
        "broker": WEBULL,
        "connected": connected,
        "gateway_online": connected,
        "brokerage_session": connected,
        "account_id": cred.account_id,
        "accounts": accounts,
        "paper": bool(config.get("paper_trading", True)),
        "last_refresh_at": cred.updated_at.isoformat() if cred.updated_at else None,
        "last_error": None if connected else f"webull {cred.status}",
    }


def _refresh_token_dead(cred: BrokerCredential) -> bool:
    """True when the refresh token is gone/expired → re-auth required."""
    if cred.auth_type == API_KEY:
        return False
    if not cred.refresh_token_enc:
        # No refresh token: only the access token keeps us alive.
        if cred.token_expires_at is None:
            return False
        expires_at = cred.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= _utcnow()
    if cred.refresh_expires_at is None:
        return False
    refresh_at = cred.refresh_expires_at
    if refresh_at.tzinfo is None:
        refresh_at = refresh_at.replace(tzinfo=timezone.utc)
    return refresh_at <= _utcnow()
