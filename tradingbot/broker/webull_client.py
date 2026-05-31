"""Real :class:`WebullClient` backed by the official ``webull-openapi-python-sdk``.

This is the *only* place that touches the SDK; it normalises Webull's shapes
into the plain dicts :class:`tradingbot.broker.webull.WebullBroker` consumes, so
the broker mapping stays SDK-agnostic and testable with a fake.

Connect API (multi-tenant OAuth) authenticates each request with the user's
short-lived (~30 min) access token *plus* the platform's app_key/app_secret HMAC
signature. The exact SDK method/field names are reconciled against real
credentials in W3 — they are isolated here on purpose. Lazily imports the SDK so
importing this module never requires the optional dependency (same pattern as
``alpaca.py`` / ``ibkr_connection.py``).

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


# Webull OAuth base URLs (Connect API). Picked by (region, paper) — paper maps to
# the UAT environment, which offers shared test accounts with no application.
_ENDPOINTS = {
    ("us", False): "us-oauth-open-api.webull.com",
    ("us", True): "us-oauth-open-api.uat.webullbroker.com",
}


def default_endpoint(region: str, paper: bool) -> str:
    return _ENDPOINTS.get((region.lower(), paper), _ENDPOINTS[("us", False)])


class SdkWebullClient:
    """Wraps the Webull SDK trade/market clients behind the WebullClient seam.

    Args:
        access_token: the user's OAuth access token (Connect API). Short-lived;
            ``token_provider`` is consulted before each call so an upstream
            refresh is picked up without rebuilding the client.
        app_key / app_secret: platform request-signing credentials.
        region: ``us`` / ``hk`` / ``jp`` / ``sg``.
        paper: route to the UAT environment.
        token_provider: optional callable returning a fresh access token.
    """

    def __init__(
        self,
        *,
        access_token: str,
        app_key: str,
        app_secret: str,
        region: str = "us",
        paper: bool = False,
        endpoint: Optional[str] = None,
        token_provider: Optional[Callable[[], str]] = None,
    ):
        self._access_token = access_token
        self._app_key = app_key
        self._app_secret = app_secret
        self._region = region
        self._paper = paper
        self._endpoint = endpoint or default_endpoint(region, paper)
        self._token_provider = token_provider
        self._trade = None
        self._mdata = None
        self._last_error: Optional[str] = None

    # -- SDK wiring (reconcile exact names against real creds in W3) ------- #

    def _clients(self):
        if self._trade is not None:
            return self._trade, self._mdata
        try:
            from webull.core.client import ApiClient
            from webull.mdata.mdata_client import MarketDataClient
            from webull.trade.trade_client import TradeClient
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "webull-openapi-python-sdk is required for WebullBroker. "
                "Install it with: pip install webull-openapi-python-sdk"
            ) from exc

        api_client = ApiClient(self._app_key, self._app_secret, self._region)
        api_client.add_endpoint(self._region, self._endpoint)
        self._apply_token(api_client)
        self._trade = TradeClient(api_client)
        self._mdata = MarketDataClient(api_client)
        self._api_client = api_client
        return self._trade, self._mdata

    def _apply_token(self, api_client) -> None:
        token = self._token_provider() if self._token_provider else self._access_token
        self._access_token = token
        # Connect API: bearer the OAuth token on every request. The exact setter
        # is SDK-version-specific; try the documented hook, fall back to a header.
        setter = getattr(api_client, "set_access_token", None)
        if callable(setter):
            setter(token)
        else:  # pragma: no cover - depends on SDK internals
            try:
                api_client.add_token(token)
            except Exception:  # noqa: BLE001
                pass

    def _refresh_token(self) -> None:
        if self._trade is not None and self._token_provider is not None:
            self._apply_token(self._api_client)

    # -- WebullClient methods (normalise SDK shapes → plain dicts) --------- #

    def account_balance(self, account_id: str) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.get_account_balance(account_id)
        d = _as_dict(raw)
        return {
            "cash": d.get("total_cash") or d.get("cash") or d.get("settled_cash"),
            "portfolio_value": d.get("net_liquidation_value") or d.get("net_asset_value"),
            "buying_power": d.get("buying_power") or d.get("day_buying_power"),
            "equity": d.get("total_market_value") or d.get("net_liquidation_value"),
        }

    def positions(self, account_id: str) -> List[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.get_account_positions(account_id)
        out: List[Dict[str, Any]] = []
        for item in _as_list(raw):
            d = _as_dict(item)
            out.append(
                {
                    "ticker": d.get("symbol") or d.get("ticker"),
                    "qty": d.get("quantity") or d.get("qty"),
                    "avg_entry_price": d.get("cost_price") or d.get("avg_cost"),
                    "current_price": d.get("last_price") or d.get("market_price"),
                    "market_value": d.get("market_value"),
                    "unrealized_pnl": d.get("unrealized_profit_loss") or d.get("unrealized_pnl"),
                    "unrealized_pnl_pct": d.get("unrealized_profit_loss_rate"),
                }
            )
        return out

    def resolve_instrument(self, symbol: str) -> str:
        trade, _ = self._clients()
        raw = trade.get_instrument(symbol, "EQUITY", self._region.upper())
        for item in _as_list(raw):
            d = _as_dict(item)
            instrument_id = d.get("instrument_id") or d.get("instrumentId")
            if instrument_id:
                return str(instrument_id)
        return ""

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        _, mdata = self._clients()
        raw = mdata.get_quote(symbol, "EQUITY")
        d = _as_dict(raw)
        return {
            "last": d.get("last") or d.get("price") or d.get("close"),
            "close": d.get("close") or d.get("pre_close"),
            "bid": d.get("bid"),
            "ask": d.get("ask"),
        }

    def preview_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.preview_order(account_id, payload)
        return _as_dict(raw)

    def place_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.place_order(account_id, payload)
        return _normalise_order(_as_dict(raw), payload)

    def cancel_order(self, account_id: str, order_id: str) -> bool:
        trade, _ = self._clients()
        self._refresh_token()
        raw = _as_dict(trade.cancel_order(account_id, order_id))
        return bool(raw.get("success", True))

    def get_order(self, account_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.get_order_detail(account_id, order_id)
        if raw is None:
            return None
        return _normalise_order(_as_dict(raw), {})

    def list_orders(self, account_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        raw = trade.list_orders(account_id, page_size=limit)
        return [_normalise_order(_as_dict(item), {}) for item in _as_list(raw)]

    def health(self) -> Dict[str, Any]:
        try:
            trade, _ = self._clients()
            self._refresh_token()
            accounts = _as_list(trade.get_account_list())
            ids = [
                _as_dict(a).get("account_id") or _as_dict(a).get("accountId")
                for a in accounts
            ]
            return {"connected": True, "accounts": [i for i in ids if i], "last_error": None}
        except Exception as exc:  # noqa: BLE001 - surfaced as health, not raised
            self._last_error = str(exc)
            return {"connected": False, "accounts": [], "last_error": str(exc)}


# --------------------------------------------------------------------------- #
# Normalisation helpers                                                        #
# --------------------------------------------------------------------------- #


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for attr in ("to_dict", "as_dict", "__dict__"):
        value = getattr(obj, attr, None)
        if callable(value):
            try:
                return dict(value())
            except Exception:  # noqa: BLE001
                continue
        if isinstance(value, dict):
            return dict(value)
    return {}


def _as_list(obj: Any) -> List[Any]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    d = _as_dict(obj)
    for key in ("items", "data", "orders", "positions", "results"):
        value = d.get(key)
        if isinstance(value, list):
            return value
    return [obj] if d else []


def _normalise_order(d: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "order_id": d.get("order_id") or d.get("orderId") or payload.get("client_order_id"),
        "client_order_id": d.get("client_order_id") or payload.get("client_order_id"),
        "ticker": d.get("symbol") or d.get("ticker"),
        "side": d.get("side") or payload.get("side"),
        "order_type": d.get("order_type") or payload.get("order_type"),
        "qty": d.get("quantity") or d.get("qty") or payload.get("qty"),
        "status": d.get("order_status") or d.get("status"),
        "filled_qty": d.get("filled_quantity") or d.get("filled_qty"),
        "filled_avg_price": d.get("avg_filled_price") or d.get("filled_avg_price"),
        "limit_price": d.get("limit_price") or payload.get("limit_price"),
    }
