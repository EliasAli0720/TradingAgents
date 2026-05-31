"""Webull Connect API OAuth 2.0 client (authorization-code flow).

Connect API is multi-tenant: each user authorises their own Webull account and
the platform exchanges the code for a short-lived (~30 min) access token plus a
rolling (~15 day) refresh token. This module builds the authorize URL and talks
to the token endpoint; it has no DB/session knowledge (that lives in the API
layer's credential repository + provider).

HTTP is injectable (``http_post``) so the flow is unit-testable without network;
the default uses ``httpx``. The exact token-endpoint paths / parameter names are
reconciled against real Connect API credentials in W3 — they are isolated to the
constants + ``_default_http_post`` here on purpose.

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md §6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode

# Connect API OAuth base URLs (paper → UAT). The path suffixes below are
# appended to these; verify both against the Connect API auth docs in W3.
_OAUTH_BASE = {
    ("us", False): "https://us-oauth-open-api.webull.com/oauth-openapi",
    ("us", True): "https://us-oauth-open-api.uat.webullbroker.com/oauth-openapi",
}

# Path suffixes on the OAuth base (verify in W3).
_AUTHORIZE_PATH = "/authorize"
_TOKEN_PATH = "/token"


def default_oauth_base(region: str, paper: bool) -> str:
    return _OAUTH_BASE.get((region.lower(), paper), _OAUTH_BASE[("us", False)])


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None          # access token lifetime, seconds
    refresh_expires_in: Optional[int] = None  # refresh token lifetime, seconds
    scope: Optional[str] = None
    account_id: Optional[str] = None

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "TokenResponse":
        return cls(
            access_token=str(data.get("access_token") or data.get("accessToken") or ""),
            refresh_token=data.get("refresh_token") or data.get("refreshToken"),
            expires_in=_as_int(data.get("expires_in") or data.get("expiresIn")),
            refresh_expires_in=_as_int(
                data.get("refresh_expires_in") or data.get("refreshExpiresIn")
            ),
            scope=data.get("scope"),
            account_id=data.get("account_id") or data.get("accountId"),
        )


@dataclass
class WebullOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str = "trade account"
    region: str = "us"
    paper: bool = False
    oauth_base: Optional[str] = None

    @property
    def base(self) -> str:
        return self.oauth_base or default_oauth_base(self.region, self.paper)


class WebullOAuthError(RuntimeError):
    pass


HttpPost = Callable[[str, Dict[str, Any], Dict[str, str]], Dict[str, Any]]


class WebullOAuthClient:
    """Builds authorize URLs and exchanges/refreshes tokens.

    Args:
        config: platform OAuth app credentials + region.
        http_post: ``(url, data, headers) -> json dict``. Injectable for tests;
            defaults to an httpx-backed POST.
    """

    def __init__(self, config: WebullOAuthConfig, http_post: Optional[HttpPost] = None):
        self._cfg = config
        self._http_post = http_post or _default_http_post

    @property
    def config(self) -> WebullOAuthConfig:
        return self._cfg

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._cfg.client_id,
            "redirect_uri": self._cfg.redirect_uri,
            "response_type": "code",
            "scope": self._cfg.scope,
            "state": state,
        }
        return f"{self._cfg.base}{_AUTHORIZE_PATH}?{urlencode(params)}"

    def exchange_code(self, code: str) -> TokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._cfg.redirect_uri,
            "client_id": self._cfg.client_id,
            "client_secret": self._cfg.client_secret,
        }
        return self._token_request(data)

    def refresh(self, refresh_token: str) -> TokenResponse:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._cfg.client_id,
            "client_secret": self._cfg.client_secret,
        }
        return self._token_request(data)

    def _token_request(self, data: Dict[str, Any]) -> TokenResponse:
        url = f"{self._cfg.base}{_TOKEN_PATH}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            payload = self._http_post(url, data, headers)
        except Exception as exc:  # noqa: BLE001 - normalise transport errors
            raise WebullOAuthError(f"token request failed: {exc}") from exc
        token = TokenResponse.from_payload(payload or {})
        if not token.access_token:
            raise WebullOAuthError(f"token response missing access_token: {payload!r}")
        return token


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_http_post(url: str, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    import httpx

    resp = httpx.post(url, data=data, headers=headers, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def oauth_client_from_config(config: dict) -> Optional[WebullOAuthClient]:
    """Build an OAuth client from the platform config, or None if unconfigured.

    Reads the shared (non-per-user) app credentials. Returns None when no
    ``webull_client_id`` is set so callers can cleanly fall back / report
    "not configured" instead of constructing a broken client.
    """
    client_id = config.get("webull_client_id")
    if not client_id:
        return None
    cfg = WebullOAuthConfig(
        client_id=str(client_id),
        client_secret=str(config.get("webull_client_secret", "")),
        redirect_uri=str(config.get("webull_redirect_uri", "")),
        scope=str(config.get("webull_scope", "trade account")),
        region=str(config.get("webull_region", "us")),
        paper=bool(config.get("paper_trading", True)),
        oauth_base=config.get("webull_oauth_base") or None,
    )
    return WebullOAuthClient(cfg)
