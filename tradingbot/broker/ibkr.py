"""Interactive Brokers broker adapter (TWS API / socket route).

Implements :class:`BrokerAdapter` on top of an :class:`IBKRConnection`
transport.  This class only maps shapes — the unified ``base.py`` models in,
IBKR shapes out — and never imports ``ib_async`` or opens a socket itself;
that lives in :mod:`tradingbot.broker.ibkr_connection`.

See docs/superpowers/specs/2026-05-29-ibkr-tws-api-integration-design.md
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from .base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from .ibkr_connection import IBKRConnection, RawOrder, RawPosition

logger = logging.getLogger(__name__)


# IBKR order status string -> our OrderStatus. Terminal/initial states only;
# partial fills are detected from filled_qty (TWS keeps status "Submitted").
_IBKR_STATUS = {
    "pendingsubmit": OrderStatus.PENDING,
    "pendingcancel": OrderStatus.PENDING,
    "presubmitted": OrderStatus.PENDING,
    "submitted": OrderStatus.PENDING,
    "apipending": OrderStatus.PENDING,
    "apicancelled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "filled": OrderStatus.FILLED,
    "inactive": OrderStatus.REJECTED,
}


def _to_order_status(ibkr_status: str, filled_qty: float, quantity: float) -> OrderStatus:
    mapped = _IBKR_STATUS.get((ibkr_status or "").lower().replace(" ", ""), OrderStatus.PENDING)
    if mapped is OrderStatus.FILLED:
        return OrderStatus.FILLED
    if mapped is OrderStatus.PENDING and 0 < filled_qty < quantity:
        return OrderStatus.PARTIALLY_FILLED
    return mapped


class IBKRBroker(BrokerAdapter):
    """IBKR implementation of :class:`BrokerAdapter` (single platform account).

    Args:
        conn: the transport (``LocalIBKRConnection`` for a live socket, or a
            Redis proxy / fake for tests).
        account_id: which IBKR account to read/trade; defaults to the primary
            managed account reported by the connection.
        paper: whether this points at a paper account (advisory flag).
    """

    def __init__(
        self,
        conn: IBKRConnection,
        account_id: Optional[str] = None,
        *,
        paper: bool = True,
    ):
        self._conn = conn
        self._account_id = account_id
        self._paper = paper
        logger.info(
            "IBKRBroker initialised (%s, account=%s)",
            "PAPER" if paper else "LIVE",
            account_id or "<primary>",
        )

    # ------------------------------------------------------------------ #
    # Account                                                              #
    # ------------------------------------------------------------------ #

    def get_account(self) -> AccountInfo:
        rows = {v.tag: v.value for v in self._conn.account_summary(self._account_id)}

        def first(*tags: str) -> float:
            for tag in tags:
                raw = rows.get(tag)
                if raw not in (None, ""):
                    try:
                        return float(raw)
                    except (TypeError, ValueError):
                        continue
            return 0.0

        return AccountInfo(
            cash=first("AvailableFunds", "TotalCashValue"),
            portfolio_value=first("NetLiquidation"),
            buying_power=first("BuyingPower", "AvailableFunds"),
            equity=first("NetLiquidation"),
        )

    # ------------------------------------------------------------------ #
    # Positions                                                            #
    # ------------------------------------------------------------------ #

    def get_positions(self) -> List[Position]:
        return [
            self._to_position(rp)
            for rp in self._conn.positions(self._account_id)
            if rp.position != 0
        ]

    def get_position(self, ticker: str) -> Optional[Position]:
        target = ticker.upper()
        for rp in self._conn.positions(self._account_id):
            if rp.position != 0 and rp.symbol.upper() == target:
                return self._to_position(rp)
        return None

    @staticmethod
    def _to_position(rp: RawPosition) -> Position:
        qty = rp.position
        avg = rp.avg_cost
        price = rp.market_price if rp.market_price is not None else avg
        market_value = (
            rp.market_value if rp.market_value is not None else price * qty
        )
        unrealized_pnl = (
            rp.unrealized_pnl
            if rp.unrealized_pnl is not None
            else (price - avg) * qty
        )
        cost_basis = abs(avg * qty)
        unrealized_pnl_pct = unrealized_pnl / cost_basis if cost_basis > 0 else 0.0
        return Position(
            ticker=rp.symbol.upper(),
            qty=qty,
            avg_entry_price=avg,
            current_price=price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            side="long" if qty >= 0 else "short",
        )

    # ------------------------------------------------------------------ #
    # Market data                                                          #
    # ------------------------------------------------------------------ #

    def get_latest_price(self, ticker: str) -> float:
        q = self._conn.quote(ticker)
        if q.last is not None:
            return q.last
        if q.bid is not None and q.ask is not None:
            return (q.bid + q.ask) / 2.0
        if q.close is not None:
            return q.close
        raise ValueError(f"No price available for {ticker!r} from IBKR")

    # ------------------------------------------------------------------ #
    # Orders                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _whole_shares(qty: float) -> int:
        shares = int(qty)
        if shares <= 0:
            raise ValueError(f"IBKR requires whole shares >= 1, got {qty}")
        return shares

    def preview_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> dict:
        """``whatIf`` margin/commission preview, shown before approval."""
        shares = self._whole_shares(qty)
        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")
        w = self._conn.what_if(
            symbol=ticker.upper(),
            side=side.value.upper(),
            quantity=shares,
            order_type=order_type.value,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=self._account_id,
        )
        return {
            "init_margin": w.init_margin,
            "maint_margin": w.maint_margin,
            "commission": w.commission,
            "equity_with_loan": w.equity_with_loan,
            "warning": w.warning,
        }

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Order:
        shares = self._whole_shares(qty)
        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")
        # Deliberately no retry on failure — never risk a duplicate order.
        raw = self._conn.place(
            symbol=ticker.upper(),
            side=side.value.upper(),
            quantity=shares,
            order_type=order_type.value,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=self._account_id,
        )
        logger.info(
            "IBKR order placed: %s %s %d %s (id=%s, status=%s)",
            side.value.upper(),
            ticker.upper(),
            shares,
            order_type.value,
            raw.order_id,
            raw.status,
        )
        return self._to_order(raw)

    def get_order(self, order_id: str) -> Order:
        raw = self._conn.order(order_id)
        if raw is None:
            raise ValueError(f"Order {order_id} not found")
        return self._to_order(raw)

    def cancel_order(self, order_id: str) -> bool:
        return self._conn.cancel(order_id)

    def get_order_history(self, limit: int = 100) -> List[Order]:
        return [self._to_order(r) for r in reversed(self._conn.recent_orders(limit))]

    @staticmethod
    def _to_order(raw: RawOrder) -> Order:
        return Order(
            order_id=raw.order_id,
            ticker=raw.symbol.upper(),
            side=OrderSide.BUY if raw.side.upper() == "BUY" else OrderSide.SELL,
            qty=raw.quantity,
            order_type=OrderType.LIMIT
            if raw.order_type.lower() == "limit"
            else OrderType.MARKET,
            status=_to_order_status(raw.status, raw.filled_qty, raw.quantity),
            submitted_at=raw.submitted_at or datetime.utcnow(),
            filled_qty=raw.filled_qty,
            filled_avg_price=raw.avg_fill_price,
            limit_price=raw.limit_price,
        )

    # ------------------------------------------------------------------ #
    # Health (IBKR-specific, used by /broker/status)                       #
    # ------------------------------------------------------------------ #

    def health(self) -> dict:
        info = dict(self._conn.health())
        info.update(account_id=self._account_id, paper=self._paper)
        return info
