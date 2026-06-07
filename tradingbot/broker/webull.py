"""Webull broker adapter — maps Webull OpenAPI shapes to the unified models.

Like :class:`IBKRBroker`, this adapter is intentionally transport-thin: it
depends on a small :class:`WebullClient` seam (a wrapper over the official
``webull-openapi-python-sdk``) rather than the SDK directly, so the business
mapping stays testable with a fake and the exact SDK call shapes live in exactly
one place (:class:`SdkWebullClient`), reconciled against real credentials later.

Webull Connect API is cloud REST (stateless per request), so — unlike IBKR —
there is no socket and no Redis connector. A :class:`WebullBroker` is built per
user from that user's OAuth access token + account id, which is why every web
process can construct its own.

Two Webull-specific facts the mapping has to handle:
  * **Orders address an ``instrument_id``, not a ticker.** We resolve
    symbol → instrument_id through the client and cache it (the instrument
    lookup is rate-limited at ~10/30s).
  * **Order placement is idempotent via ``client_order_id``** — we never
    auto-retry a place (avoids duplicate orders), mirroring the IBKR adapter.

See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

from .base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


# --------------------------------------------------------------------------- #
# Client seam                                                                 #
#                                                                             #
# The client returns *normalised* dicts (our field names) so the broker        #
# mapping never sees raw SDK shapes. Order status is passed through as the raw  #
# Webull string so the enum mapping is exercised (and tested) in the broker.   #
# --------------------------------------------------------------------------- #


@runtime_checkable
class WebullClient(Protocol):
    """Everything :class:`WebullBroker` needs from the Webull SDK."""

    def account_balance(self, account_id: str) -> Dict[str, Any]:
        """``{cash, portfolio_value, buying_power, equity}`` for *account_id*."""
        ...

    def positions(self, account_id: str) -> List[Dict[str, Any]]:
        """Open positions; each a dict with ticker/qty/prices/pnl fields."""
        ...

    def resolve_instrument(self, symbol: str) -> str:
        """Map a ticker to a Webull ``instrument_id`` (rate-limited upstream)."""
        ...

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """``{last?, close?, bid?, ask?, price?}`` market-data snapshot."""
        ...

    def preview_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Cost / buying-power preview for an order (no placement)."""
        ...

    def place_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order; return its initial normalised order dict."""
        ...

    def cancel_order(self, account_id: str, order_id: str) -> bool:
        """Cancel an open order. True if accepted."""
        ...

    def get_order(self, account_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Look up a single order, or None."""
        ...

    def list_orders(self, account_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Recent orders, newest last."""
        ...

    def health(self) -> Dict[str, Any]:
        """Connectivity / token facts: ``{connected, accounts?, last_error?}``."""
        ...


# Webull order-status strings → our unified OrderStatus. Compared lower-cased so
# minor casing/spelling variants ("Canceled"/"Cancelled") both land correctly.
_STATUS_MAP = {
    "filled": OrderStatus.FILLED,
    "partiallyfilled": OrderStatus.PARTIALLY_FILLED,
    "partialfilled": OrderStatus.PARTIALLY_FILLED,
    "partial_filled": OrderStatus.PARTIALLY_FILLED,
    "cancelled": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
    "pending": OrderStatus.PENDING,
    "working": OrderStatus.PENDING,
    "submitted": OrderStatus.PENDING,
    "pendingsubmit": OrderStatus.PENDING,
    "pendingnew": OrderStatus.PENDING,
    "new": OrderStatus.PENDING,
    "rejected": OrderStatus.REJECTED,
    "failed": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
}


def _f(value: Any) -> Optional[float]:
    """Best-effort float; Webull sends numbers as strings."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _f0(value: Any) -> float:
    return _f(value) or 0.0


class WebullBroker(BrokerAdapter):
    """Maps Webull OpenAPI data into the unified broker models via a client."""

    def __init__(
        self,
        client: WebullClient,
        account_id: str,
        *,
        region: str = "us",
        paper: bool = False,
    ):
        self._client = client
        self._account_id = account_id
        self._region = region
        self._paper = paper
        self._instrument_cache: Dict[str, str] = {}

    # -- instrument resolution (cached; lookup is rate-limited upstream) --- #

    def _instrument_id(self, symbol: str) -> str:
        key = symbol.upper()
        cached = self._instrument_cache.get(key)
        if cached is not None:
            return cached
        instrument_id = self._client.resolve_instrument(key)
        if not instrument_id:
            raise ValueError(f"Could not resolve Webull instrument for {symbol!r}")
        self._instrument_cache[key] = instrument_id
        return instrument_id

    # -- account ---------------------------------------------------------- #

    def get_account(self) -> AccountInfo:
        a = self._client.account_balance(self._account_id)
        net_liq = _f0(a.get("portfolio_value"))
        return AccountInfo(
            cash=_f0(a.get("cash")),
            portfolio_value=net_liq,
            buying_power=_f0(a.get("buying_power")),
            equity=_f(a.get("equity")) or net_liq,
        )

    # -- positions -------------------------------------------------------- #

    def get_positions(self) -> List[Position]:
        return [self._to_position(p) for p in self._client.positions(self._account_id)]

    def get_position(self, ticker: str) -> Optional[Position]:
        target = ticker.upper()
        for p in self._client.positions(self._account_id):
            if str(p.get("ticker", "")).upper() == target:
                return self._to_position(p)
        return None

    @staticmethod
    def _to_position(p: Dict[str, Any]) -> Position:
        qty = _f0(p.get("qty"))
        avg = _f0(p.get("avg_entry_price"))
        price = _f(p.get("current_price"))
        if price is None:
            price = avg
        market_value = _f(p.get("market_value"))
        if market_value is None:
            market_value = qty * price
        unrealized = _f0(p.get("unrealized_pnl"))
        unrealized_pct = _f(p.get("unrealized_pnl_pct"))
        if unrealized_pct is None:
            cost_basis = abs(avg * qty)
            unrealized_pct = (unrealized / cost_basis) if cost_basis else 0.0
        return Position(
            ticker=str(p.get("ticker", "")),
            qty=qty,
            avg_entry_price=avg,
            current_price=price,
            market_value=market_value,
            unrealized_pnl=unrealized,
            unrealized_pnl_pct=unrealized_pct,
            side="long" if qty >= 0 else "short",
        )

    # -- orders ----------------------------------------------------------- #

    def _order_payload(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType,
        limit_price: Optional[float],
        time_in_force: str,
        client_order_id: Optional[str],
    ) -> Dict[str, Any]:
        if qty <= 0:
            raise ValueError("quantity must be greater than zero")
        if limit_price is not None and limit_price <= 0:
            raise ValueError("limit_price must be greater than zero")
        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")
        symbol = ticker.upper()
        tif = (time_in_force or "day").upper()
        quantity = str(qty)
        payload: Dict[str, Any] = {
            "client_order_id": client_order_id or uuid4().hex,
            "instrument_id": self._instrument_id(symbol),
            "symbol": symbol,
            "instrument_type": "EQUITY",
            "side": "BUY" if side == OrderSide.BUY else "SELL",
            "order_type": order_type.value.upper(),
            "tif": tif,
            "time_in_force": tif,
            "qty": quantity,
            "quantity": quantity,
            "entrust_type": "QTY",
            "combo_type": "NORMAL",
            "support_trading_session": "CORE",
            # market: required — the SDK builds the request "category" header
            # from it (``<market>_STOCK``); omitting it crashes place/preview.
            "market": self._region.upper(),
            # Market orders must be regular-hours only; allow it for limit orders.
            "extended_hours_trading": False,
        }
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        return payload

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        client_order_id: Optional[str] = None,
    ) -> Order:
        payload = self._order_payload(
            ticker, qty, side, order_type, limit_price, time_in_force, client_order_id
        )
        # No auto-retry: a failed place must surface so we never double-submit.
        raw = self._client.place_order(self._account_id, payload)
        return self._to_order(raw, fallback_ticker=ticker)

    def get_order(self, order_id: str) -> Order:
        raw = self._client.get_order(self._account_id, order_id)
        if raw is None:
            raise ValueError(f"Order {order_id!r} not found")
        return self._to_order(raw)

    def cancel_order(self, order_id: str) -> bool:
        try:
            return bool(self._client.cancel_order(self._account_id, order_id))
        except Exception:  # noqa: BLE001 - cancel is best-effort
            return False

    def get_order_history(self, limit: int = 100) -> List[Order]:
        orders = [self._to_order(r) for r in self._client.list_orders(self._account_id, limit)]
        orders.reverse()  # client returns newest last; history is newest first
        return orders

    # -- order preview ---------------------------------------------------- #

    def preview_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> dict:
        payload = self._order_payload(
            ticker, qty, side, order_type, limit_price, time_in_force, None
        )
        out = self._client.preview_order(self._account_id, payload) or {}
        # Normalise onto the same preview shape the IBKR whatIf path returns, so
        # the approval/UI layer is broker-agnostic.
        return {
            "init_margin": _f(out.get("init_margin")),
            "maint_margin": _f(out.get("maint_margin")),
            "commission": _f(out.get("commission") or out.get("est_commission")),
            "equity_with_loan": _f(out.get("equity_with_loan")),
            "estimated_cost": _f(out.get("estimated_cost") or out.get("est_cost")),
            "buying_power": _f(out.get("buying_power")),
            "warning": out.get("warning") or out.get("warning_text") or None,
        }

    # -- market data ------------------------------------------------------ #

    def get_latest_price(self, ticker: str) -> float:
        q = self._client.get_quote(ticker)
        price = (
            _f(q.get("price"))
            or _f(q.get("last"))
            or _f(q.get("close"))
            or _f(q.get("ask"))
            or _f(q.get("bid"))
        )
        if price is None:
            raise ValueError(f"No price available for {ticker!r}")
        return price

    # -- health ----------------------------------------------------------- #

    def health(self) -> dict:
        try:
            h = self._client.health()
        except Exception as exc:  # noqa: BLE001 - report rather than raise
            return {"gateway_online": False, "accounts": [], "last_error": str(exc)}
        online = bool(h.get("connected", False))
        return {
            "gateway_online": online,
            "accounts": h.get("accounts") or ([self._account_id] if self._account_id else []),
            "last_error": h.get("last_error"),
        }

    # -- mapping ---------------------------------------------------------- #

    @staticmethod
    def _to_order(raw: Dict[str, Any], *, fallback_ticker: str = "") -> Order:
        status_key = str(raw.get("status", "")).lower().replace(" ", "")
        status = _STATUS_MAP.get(status_key, OrderStatus.PENDING)
        qty = _f0(raw.get("qty"))
        filled = _f0(raw.get("filled_qty"))
        # Webull may report "Filled" before the full qty settles; treat a partial
        # fill consistently with the IBKR adapter.
        if status == OrderStatus.FILLED and filled and qty and filled < qty:
            status = OrderStatus.PARTIALLY_FILLED
        side = "buy" if str(raw.get("side", "buy")).upper() == "BUY" else "sell"
        otype = "limit" if "limit" in str(raw.get("order_type", "")).lower() else "market"
        submitted = raw.get("submitted_at")
        if not isinstance(submitted, datetime):
            submitted = datetime.now(timezone.utc)
        return Order(
            order_id=str(raw.get("order_id") or raw.get("client_order_id") or ""),
            ticker=str(raw.get("ticker") or fallback_ticker),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            qty=qty,
            order_type=OrderType.LIMIT if otype == "limit" else OrderType.MARKET,
            status=status,
            submitted_at=submitted,
            filled_qty=filled,
            filled_avg_price=_f(raw.get("filled_avg_price")),
            limit_price=_f(raw.get("limit_price")),
        )
