"""Read-only broker backed by a point-in-time snapshot from the local sidecar.

In the desktop split (server builds the proposal + risk verdict, the local TWS
executes), the server has no socket to the user's account. The desktop pushes
the live account / positions / price into this adapter so the existing
``TradeProposalBuilder`` and ``RiskGate`` run unchanged on the server. Order
placement is intentionally unsupported — execution happens on the local sidecar.

See docs/superpowers/specs/2026-05-30-electron-desktop-local-broker-design.md §6
"""

from __future__ import annotations

from typing import List, Mapping, Optional

from .base import AccountInfo, BrokerAdapter, Order, OrderSide, OrderType, Position


class SnapshotBroker(BrokerAdapter):
    def __init__(
        self,
        account: AccountInfo,
        positions: List[Position],
        prices: Mapping[str, float],
    ):
        self._account = account
        self._positions = list(positions)
        self._prices = {k.upper(): float(v) for k, v in prices.items()}

    # -- reads (what the builder + RiskGate need) ------------------------- #

    def get_account(self) -> AccountInfo:
        return self._account

    def get_positions(self) -> List[Position]:
        return list(self._positions)

    def get_position(self, ticker: str) -> Optional[Position]:
        target = ticker.upper()
        for pos in self._positions:
            if pos.ticker.upper() == target:
                return pos
        return None

    def get_latest_price(self, ticker: str) -> float:
        target = ticker.upper()
        if target in self._prices:
            return self._prices[target]
        pos = self.get_position(target)
        if pos is not None and pos.current_price:
            return pos.current_price
        raise ValueError(f"No snapshot price for {ticker!r}")

    # -- writes (unsupported: execution is local) ------------------------- #

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Order:
        raise NotImplementedError("SnapshotBroker is read-only; execution is local")

    def get_order(self, order_id: str) -> Order:
        raise NotImplementedError("SnapshotBroker is read-only; execution is local")

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("SnapshotBroker is read-only; execution is local")

    def get_order_history(self, limit: int = 100) -> List[Order]:
        return []
