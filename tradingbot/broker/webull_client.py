"""Real :class:`WebullClient` backed by the official ``webull-openapi-python-sdk``.

This is the *only* place that touches the SDK; it normalises Webull's shapes
into the plain dicts :class:`tradingbot.broker.webull.WebullBroker` consumes, so
the broker mapping stays SDK-agnostic and testable with a fake.

Connect API (multi-tenant OAuth) authenticates each request with the user's
short-lived (~30 min) access token *plus* the platform's app_key/app_secret HMAC
signature. Trading API direct mode authenticates with a user's own
app_key/app_secret and no OAuth token. The exact SDK method/field names are
reconciled against real credentials in W3 — they are isolated here on purpose.
Lazily imports the SDK so importing this module never requires the optional
dependency (same pattern as ``alpaca.py`` / ``ibkr_connection.py``).

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
        access_token: the user's OAuth access token (Connect API). Empty in
            Trading API direct mode.
        app_key / app_secret: request-signing credentials. Shared platform
            credentials for OAuth; user-supplied credentials for direct mode.
        auth_type: ``oauth`` or ``api_key``.
        region: ``us`` / ``hk`` / ``jp`` / ``sg``.
        paper: route to the UAT environment.
        token_provider: optional callable returning a fresh access token.
        connect_timeout / read_timeout: HTTP timeouts (seconds) handed to the
            SDK's ApiClient. The SDK defaults (5s connect / 10s read) are too
            tight for cross-border / proxied calls to Webull's API, so we
            default higher and let callers raise them further via config.
    """

    def __init__(
        self,
        *,
        access_token: str,
        app_key: str,
        app_secret: str,
        auth_type: str = "oauth",
        region: str = "us",
        paper: bool = False,
        endpoint: Optional[str] = None,
        token_provider: Optional[Callable[[], str]] = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
    ):
        self._access_token = access_token
        self._app_key = app_key
        self._app_secret = app_secret
        self._auth_type = auth_type
        self._region = region
        self._paper = paper
        self._endpoint = endpoint or (
            default_endpoint(region, paper) if auth_type == "oauth" else None
        )
        self._token_provider = token_provider
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._trade = None
        self._mdata = None
        self._last_error: Optional[str] = None

    # -- SDK wiring (reconcile exact names against real creds in W3) ------- #

    def _clients(self):
        if self._trade is not None:
            return self._trade, self._mdata
        try:
            from webull.core.client import ApiClient
            from webull.trade.trade_client import TradeClient
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "webull-openapi-python-sdk is required for WebullBroker. "
                "Install it with: pip install webull-openapi-python-sdk"
            ) from exc
        try:
            from webull.data.data_client import DataClient as MarketDataClient
        except ImportError:
            try:
                from webull.mdata.mdata_client import MarketDataClient
            except ImportError as exc:  # pragma: no cover - SDK version guard
                raise ImportError(
                    "webull-openapi-python-sdk market data client is unavailable. "
                    "Use SDK 2.x on Python 3.13, or run SDK 1.x on Python 3.11."
                ) from exc

        api_client = ApiClient(
            self._app_key,
            self._app_secret,
            self._region,
            connect_timeout=self._connect_timeout,
            timeout=self._read_timeout,
        )
        if self._endpoint:
            api_client.add_endpoint(self._region, self._endpoint)
        self._apply_token(api_client)
        self._trade = TradeClient(api_client)
        self._mdata = MarketDataClient(api_client)
        self._api_client = api_client
        return self._trade, self._mdata

    def _apply_token(self, api_client) -> None:
        if self._auth_type != "oauth":
            return
        token = self._token_provider() if self._token_provider else self._access_token
        if not token:
            return
        self._access_token = token
        # Connect API: bearer the OAuth token on every request. The exact setter
        # is SDK-version-specific; try the documented hook, fall back to a header.
        for name in ("set_token", "set_access_token", "add_token"):
            setter = getattr(api_client, name, None)
            if callable(setter):
                setter(token)
                return

    def _refresh_token(self) -> None:
        if self._trade is not None and self._token_provider is not None:
            self._apply_token(self._api_client)

    # -- WebullClient methods (normalise SDK shapes → plain dicts) --------- #

    def account_balance(self, account_id: str) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        account_api = getattr(trade, "account_v2", trade)
        # Webull's /openapi/assets/balance nests the real figures inside a
        # per-currency list (``account_currency_assets``); merge the relevant
        # entry up so the field lookups below see them. Top-level fields (used by
        # the test fakes) still win when present.
        d = _flatten_balance(_as_dict(account_api.get_account_balance(account_id)))
        return {
            "cash": _pick(d, "total_cash", "cash", "cash_balance", "settled_cash", "total_cash_value"),
            "portfolio_value": _pick(
                d, "net_liquidation_value", "net_asset_value", "total_asset", "total_market_value"
            ),
            "buying_power": _pick(d, "buying_power", "day_buying_power", "available_buying_power"),
            "equity": _pick(
                d, "total_market_value", "market_value", "net_liquidation_value", "total_asset"
            ),
        }

    def positions(self, account_id: str) -> List[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        account_api = getattr(trade, "account_v2", trade)
        get_positions = (
            getattr(account_api, "get_account_position", None)
            or getattr(account_api, "get_account_positions")
        )
        raw = get_positions(account_id)
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
        trade, mdata = self._clients()
        if hasattr(mdata, "instrument"):
            raw = mdata.instrument.get_instrument(symbols=symbol, category="US_STOCK")
        else:
            raw = trade.get_instrument(symbol, "EQUITY", self._region.upper())
        for item in _as_list(raw):
            d = _as_dict(item)
            instrument_id = d.get("instrument_id") or d.get("instrumentId")
            if instrument_id:
                return str(instrument_id)
        return ""

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        _, mdata = self._clients()
        market_data = getattr(mdata, "market_data", mdata)
        snapshot = {}
        get_snapshot = getattr(market_data, "get_snapshot", None)
        if callable(get_snapshot):
            snapshot = _normalise_quote(_first_dict(get_snapshot(symbol, "US_STOCK")))
            if snapshot.get("price") or snapshot.get("last"):
                return snapshot

        if hasattr(mdata, "market_data"):
            raw = market_data.get_quotes(symbol, "US_STOCK")
        else:
            raw = mdata.get_quote(symbol, "EQUITY")
        quote = _normalise_quote(_first_dict(raw))
        return {**quote, **{k: v for k, v in snapshot.items() if quote.get(k) is None and v is not None}}

    def preview_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        order_api = getattr(trade, "order_v2", trade)
        if order_api is not trade:
            raw = order_api.preview_order(account_id, [payload])
        else:
            raw = order_api.preview_order(account_id, payload)
        return _as_dict(raw)

    def place_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade, _ = self._clients()
        self._refresh_token()
        order_api = getattr(trade, "order_v2", trade)
        if order_api is not trade:
            raw = order_api.place_order(account_id, [payload])
        else:
            raw = order_api.place_order(account_id, payload)
        return _normalise_order(_as_dict(raw), payload)

    def cancel_order(self, account_id: str, order_id: str) -> bool:
        trade, _ = self._clients()
        self._refresh_token()
        order_api = getattr(trade, "order_v2", trade)
        raw = _as_dict(order_api.cancel_order(account_id, order_id))
        return bool(raw.get("success", True))

    def get_order(self, account_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        order_api = getattr(trade, "order_v2", trade)
        raw = order_api.get_order_detail(account_id, order_id)
        if raw is None:
            return None
        return _normalise_order(_as_dict(raw), {})

    def list_orders(self, account_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        trade, _ = self._clients()
        self._refresh_token()
        order_api = getattr(trade, "order_v2", trade)
        if hasattr(order_api, "get_order_open"):
            raw = order_api.get_order_open(account_id, page_size=limit)
        else:
            raw = order_api.list_orders(account_id, page_size=limit)
        return [_normalise_order(_as_dict(item), {}) for item in _as_list(raw)]

    def health(self) -> Dict[str, Any]:
        try:
            trade, _ = self._clients()
            self._refresh_token()
            account_api = getattr(trade, "account_v2", trade)
            accounts = _as_list(account_api.get_account_list())
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


def _payload(obj: Any) -> Any:
    """Unwrap a ``requests.Response`` (what the Webull SDK returns) to its parsed
    JSON body. Anything else (already a dict/list, or a list item) passes through.

    The SDK's ``ApiClient.get_response`` returns the raw ``requests.Response``;
    non-2xx responses already raise inside the SDK, so a Response that reaches
    here is a successful call whose JSON payload holds the real data.
    """
    if obj is not None and hasattr(obj, "status_code") and callable(getattr(obj, "json", None)):
        try:
            return obj.json()
        except Exception:  # noqa: BLE001 - malformed/empty body
            return {}
    return obj


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    """First present, non-empty value among *keys* (tries camelCase too)."""
    for key in keys:
        for k in (key, _camel(key)):
            v = d.get(k)
            if v is not None and v != "":
                return v
    return None


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(w.capitalize() for w in rest)


def _flatten_balance(d: Dict[str, Any]) -> Dict[str, Any]:
    """Merge Webull's per-currency balance entry up to the top level.

    ``/openapi/assets/balance`` returns the headline figures inside
    ``account_currency_assets: [{currency, cash_balance, ...}]``. Pick the entry
    matching ``total_asset_currency`` (else the first) and overlay it, so the
    flat field lookups in :meth:`account_balance` find real numbers.
    """
    for key in ("account_currency_assets", "accountCurrencyAssets", "currency_assets", "assets"):
        items = d.get(key)
        if isinstance(items, list) and items:
            preferred = d.get("total_asset_currency") or d.get("totalAssetCurrency")
            chosen = next(
                (x for x in items if isinstance(x, dict) and x.get("currency") == preferred),
                None,
            ) or items[0]
            if isinstance(chosen, dict):
                return {**d, **chosen}
    return d


def _first_dict(obj: Any) -> Dict[str, Any]:
    items = _as_list(obj)
    if items:
        return _as_dict(items[0])
    return _as_dict(obj)


def _as_dict(obj: Any) -> Dict[str, Any]:
    obj = _payload(obj)
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
    obj = _payload(obj)
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    d = _as_dict(obj)
    for key in ("items", "data", "accounts", "account_list", "accountList",
                "orders", "positions", "holdings", "holding_list", "results"):
        value = d.get(key)
        if isinstance(value, list):
            return value
    return [obj] if d else []


def _level_price(value: Any) -> Any:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        return _pick(value, "price", "bid_price", "ask_price")
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _normalise_quote(d: Dict[str, Any]) -> Dict[str, Any]:
    price = _pick(
        d,
        "price",
        "last",
        "last_price",
        "last_trade_price",
        "trade_price",
        "latest_price",
        "close",
    )
    return {
        "price": price,
        "last": _pick(d, "last", "last_price", "last_trade_price", "trade_price") or price,
        "close": _pick(d, "close", "pre_close", "previous_close", "prev_close"),
        "bid": _pick(d, "bid", "bid_price", "best_bid", "best_bid_price")
        or _level_price(d.get("bids") or d.get("bid_list") or d.get("bidList")),
        "ask": _pick(d, "ask", "ask_price", "best_ask", "best_ask_price")
        or _level_price(d.get("asks") or d.get("ask_list") or d.get("askList")),
    }


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
