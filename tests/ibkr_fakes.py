"""Shared in-memory IBKRConnection fake for broker tests (not collected)."""

from __future__ import annotations

from typing import List, Optional

from tradingbot.broker.ibkr_connection import (
    AccountValue,
    Quote,
    RawOrder,
    RawPosition,
    WhatIfResult,
)


class FakeIBKRConnection:
    """Implements the full IBKRConnection protocol with canned data.

    Order placement records calls and synthesises a RawOrder so the broker
    mapping can be exercised without ib_async or a live gateway.
    """

    def __init__(
        self,
        *,
        summary: Optional[List[AccountValue]] = None,
        positions: Optional[List[RawPosition]] = None,
        quote: Optional[Quote] = None,
        accounts: Optional[List[str]] = None,
        whatif: Optional[WhatIfResult] = None,
        place_raises: Optional[Exception] = None,
    ):
        self._summary = summary or []
        self._positions = positions or []
        self._quote = quote or Quote()
        self._accounts = accounts or ["DU1234567"]
        self._whatif = whatif or WhatIfResult(init_margin=100.0, commission=1.0)
        self._place_raises = place_raises
        self.connected = False
        self._orders: dict[str, RawOrder] = {}
        self.place_calls = 0
        self.whatif_calls = 0
        self.cancelled: list[str] = []
        self._seq = 0

    # -- reads --
    def ensure_connected(self) -> None:
        self.connected = True

    def managed_accounts(self) -> List[str]:
        return self._accounts

    def account_summary(self, account_id: Optional[str] = None) -> List[AccountValue]:
        return self._summary

    def positions(self, account_id: Optional[str] = None) -> List[RawPosition]:
        return self._positions

    def quote(self, symbol: str) -> Quote:
        return self._quote

    def health(self) -> dict:
        return {"gateway_online": self.connected, "accounts": self._accounts, "last_error": None}

    # -- orders --
    def what_if(self, symbol, side, quantity, order_type, limit_price=None, time_in_force="day", account=None):
        self.whatif_calls += 1
        return self._whatif

    def place(self, symbol, side, quantity, order_type, limit_price=None, time_in_force="day", account=None):
        self.place_calls += 1
        if self._place_raises is not None:
            raise self._place_raises
        self._seq += 1
        oid = f"O{self._seq}"
        raw = RawOrder(
            order_id=oid,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=float(quantity),
            status="Submitted",
            filled_qty=0.0,
            avg_fill_price=None,
            limit_price=limit_price,
            time_in_force=time_in_force,
        )
        self._orders[oid] = raw
        return raw

    def cancel(self, order_id: str) -> bool:
        self.cancelled.append(order_id)
        return order_id in self._orders

    def order(self, order_id: str) -> Optional[RawOrder]:
        return self._orders.get(order_id)

    def open_orders(self) -> List[RawOrder]:
        return [o for o in self._orders.values() if o.status in ("Submitted", "PreSubmitted")]

    def recent_orders(self, limit: int = 100) -> List[RawOrder]:
        return list(self._orders.values())[-limit:]
