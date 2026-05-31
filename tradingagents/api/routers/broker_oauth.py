"""Webull Connect API OAuth endpoints (per-user authorization).

Multi-tenant flow: a logged-in user authorises their own Webull account; the
server exchanges the code for tokens and stores them encrypted, scoped to that
user. All other ``/broker/*`` endpoints then transparently use the Webull
broker for that user (see ``broker_provider``).

Endpoints (prefix ``/broker/oauth/webull``):
  GET  /authorize   → returns the Webull authorize URL (frontend navigates to it)
  GET  /callback    → Webull redirects here with ?code&state; exchanges + stores
  POST /refresh     → force a token refresh (returns status)
  POST /disconnect  → revoke the stored credential
  GET  /status      → connection status for this user's Webull credential

State is a Fernet-encrypted, time-limited token binding the flow to one user, so
``/callback`` cannot be replayed or bound to another account.

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md §6
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tradingagents.api.broker_credential_repository import (
    CONNECTED,
    WEBULL,
    BrokerCredentialRepository,
)
from tradingagents.api.crypto import decrypt_secret, encrypt_secret
from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.models import User
from tradingagents.api.routers.broker import get_config

router = APIRouter(prefix="/broker/oauth/webull", tags=["broker-oauth"])

# OAuth state lifetime — the user has this long to complete the Webull login.
_STATE_TTL_SECONDS = 600


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class AuthorizeResponse(BaseModel):
    authorize_url: str


class WebullStatusResponse(BaseModel):
    connected: bool
    status: str  # connected | expired | revoked | not_connected
    account_id: Optional[str] = None
    region: Optional[str] = None
    scope: Optional[str] = None
    token_expires_at: Optional[str] = None


# --------------------------------------------------------------------------- #
# Dependencies (overridable in tests)                                         #
# --------------------------------------------------------------------------- #


def get_oauth_client(config: dict = Depends(get_config)):
    from tradingbot.broker.webull_oauth import oauth_client_from_config

    client = oauth_client_from_config(config)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webull OAuth is not configured",
        )
    return client


# --------------------------------------------------------------------------- #
# State signing (Fernet-encrypted, time-limited, user-bound)                  #
# --------------------------------------------------------------------------- #


def _encode_state(user_id: str) -> str:
    payload = json.dumps({"u": user_id, "t": datetime.now(timezone.utc).timestamp()})
    return encrypt_secret(payload)


def _decode_state(state: str) -> str:
    try:
        payload = json.loads(decrypt_secret(state))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid state") from exc
    issued = float(payload.get("t", 0))
    if datetime.now(timezone.utc).timestamp() - issued > _STATE_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="state expired")
    user_id = payload.get("u")
    if not user_id:
        raise HTTPException(status_code=400, detail="invalid state")
    return str(user_id)


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #


@router.get("/authorize", response_model=AuthorizeResponse)
def authorize(
    user: User = Depends(get_current_user),
    oauth_client=Depends(get_oauth_client),
):
    return AuthorizeResponse(authorize_url=oauth_client.authorize_url(_encode_state(user.user_id)))


@router.get("/callback")
def callback(
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config),
    oauth_client=Depends(get_oauth_client),
):
    from tradingbot.broker.webull_oauth import WebullOAuthError

    user_id = _decode_state(state)
    try:
        token = oauth_client.exchange_code(code)
    except WebullOAuthError as exc:
        return _redirect(config, ok=False, detail=str(exc))

    repo = BrokerCredentialRepository(session, user_id)
    repo.upsert(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_in=token.expires_in,
        refresh_expires_in=token.refresh_expires_in,
        account_id=token.account_id,
        region=str(config.get("webull_region", "us")),
        scope=token.scope or oauth_client.config.scope,
    )
    session.commit()
    return _redirect(config, ok=True)


@router.post("/refresh", response_model=WebullStatusResponse)
def refresh(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    oauth_client=Depends(get_oauth_client),
):
    from tradingbot.broker.webull_oauth import WebullOAuthError

    repo = BrokerCredentialRepository(session, user.user_id)
    cred = repo.get(WEBULL)
    if cred is None:
        raise HTTPException(status_code=404, detail="not connected")
    refresh_token = repo.refresh_token(cred)
    if not refresh_token:
        repo.mark_expired(WEBULL)
        session.commit()
        raise HTTPException(status_code=409, detail="no refresh token; reconnect required")
    try:
        token = oauth_client.refresh(refresh_token)
    except WebullOAuthError as exc:
        repo.mark_expired(WEBULL)
        session.commit()
        raise HTTPException(status_code=409, detail=f"refresh failed: {exc}") from exc
    repo.update_tokens(
        cred,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_in=token.expires_in,
        refresh_expires_in=token.refresh_expires_in,
    )
    session.commit()
    return _status_resp(repo.get(WEBULL))


@router.post("/disconnect", response_model=WebullStatusResponse)
def disconnect(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    repo = BrokerCredentialRepository(session, user.user_id)
    repo.revoke(WEBULL)
    session.commit()
    return _status_resp(repo.get(WEBULL))


@router.get("/status", response_model=WebullStatusResponse)
def webull_status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    repo = BrokerCredentialRepository(session, user.user_id)
    return _status_resp(repo.get(WEBULL))


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _redirect(config: dict, *, ok: bool, detail: str = "") -> RedirectResponse:
    base = str(config.get("webull_post_auth_redirect", "/broker")) or "/broker"
    sep = "&" if "?" in base else "?"
    suffix = "connected=webull" if ok else f"error={_q(detail) or 'webull_auth_failed'}"
    return RedirectResponse(url=f"{base}{sep}{suffix}", status_code=302)


def _q(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _status_resp(cred) -> WebullStatusResponse:
    if cred is None:
        return WebullStatusResponse(connected=False, status="not_connected")
    return WebullStatusResponse(
        connected=cred.status == CONNECTED,
        status=cred.status,
        account_id=cred.account_id,
        region=cred.region,
        scope=cred.scope,
        token_expires_at=cred.token_expires_at.isoformat() if cred.token_expires_at else None,
    )
