"""Transport abstraction between :class:`IBKRBroker` and Interactive Brokers.

``IBKRBroker`` only ever does *business mapping* (IBKR shapes -> the unified
``base.py`` models).  *How* we actually talk to IBKR — a live ``ib_async``
socket to a local TWS/Gateway, or a Redis-proxied command channel to the
single connector process — lives behind the :class:`IBKRConnection` protocol.
This keeps the broker testable with a fake and lets us swap the transport
(local socket vs Redis proxy, OAuth later) without touching the mapping or the
layers above (``AutoTrader``, factory, API).

See docs/superpowers/specs/2026-05-29-ibkr-tws-api-integration-design.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# Transport-neutral value objects                                             #
#                                                                             #
# The protocol returns these (not raw ib_async types) so the broker mapping   #
# and the fake stay decoupled from the IBKR client library.                   #
# --------------------------------------------------------------------------- #


@dataclass
class AccountValue:
    """One row of the IBKR account summary (e.g. tag=NetLiquidation)."""

    tag: str
    value: str
    currency: str = ""


@dataclass
class RawPosition:
    """A position as IBKR reports it, before mapping to ``base.Position``."""

    symbol: str
    conid: int
    position: float
    avg_cost: float
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    currency: str = ""


@dataclass
class Quote:
    """A lightweight market-data snapshot for one contract."""

    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    close: Optional[float] = None


@dataclass
class RawOrder:
    """An order as IBKR reports it, before mapping to ``base.Order``."""

    order_id: str
    symbol: str
    side: str  # "BUY" / "SELL"
    order_type: str  # "market" / "limit"
    quantity: float
    status: str  # IBKR status string (Submitted/Filled/Cancelled/...)
    filled_qty: float = 0.0
    avg_fill_price: Optional[float] = None
    limit_price: Optional[float] = None
    time_in_force: str = "day"
    submitted_at: Optional[datetime] = None
    conid: Optional[int] = None


@dataclass
class WhatIfResult:
    """Margin / commission preview returned by IBKR ``whatIfOrder``."""

    init_margin: Optional[float] = None
    maint_margin: Optional[float] = None
    commission: Optional[float] = None
    equity_with_loan: Optional[float] = None
    warning: Optional[str] = None


def nan_to_none(value) -> Optional[float]:
    """ib_async fills missing numeric ticks with NaN — normalise to None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


@runtime_checkable
class IBKRConnection(Protocol):
    """Everything :class:`IBKRBroker` needs from a transport."""

    def ensure_connected(self) -> None:
        """Establish the connection if not already up. Idempotent."""
        ...

    def managed_accounts(self) -> List[str]:
        """Account ids visible to this login (e.g. ``['DU1234567']``)."""
        ...

    def account_summary(self, account_id: Optional[str] = None) -> List[AccountValue]:
        """Summary rows for *account_id* (or the primary account if None)."""
        ...

    def positions(self, account_id: Optional[str] = None) -> List[RawPosition]:
        """Open positions for *account_id* (or the primary account if None)."""
        ...

    def quote(self, symbol: str) -> Quote:
        """A market-data snapshot for a US-listed stock *symbol*."""
        ...

    def what_if(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> WhatIfResult:
        """Preview margin/commission impact of an order without placing it."""
        ...

    def place(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> RawOrder:
        """Place an order and return its initial state."""
        ...

    def cancel(self, order_id: str) -> bool:
        """Cancel an open order. True if an open order was found and cancelled."""
        ...

    def order(self, order_id: str) -> Optional[RawOrder]:
        """Look up a single order by id, or None."""
        ...

    def open_orders(self) -> List[RawOrder]:
        """Currently-open orders (for reconciliation)."""
        ...

    def recent_orders(self, limit: int = 100) -> List[RawOrder]:
        """Recent orders this session, newest last (for history)."""
        ...

    def health(self) -> dict:
        """Connectivity facts: connected? account? error?"""
        ...


class LocalIBKRConnection:
    """Live :class:`IBKRConnection` backed by an ``ib_async`` socket.

    Talks to a TWS / IB Gateway running on this host (or reachable on the
    private network).  Used by the single connector process and by local
    CLI / dev runs.  Lazily imports ``ib_async`` so the rest of the system
    keeps importing cleanly when the IBKR extra is not installed — same
    pattern as :class:`AlpacaBroker`.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        *,
        market_data_type: int = 3,
        connect_timeout: float = 10.0,
        snapshot_wait: float = 2.5,
        order_ack_wait: float = 1.0,
        whatif_timeout: float = 12.0,
    ):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._market_data_type = market_data_type
        self._connect_timeout = connect_timeout
        self._snapshot_wait = snapshot_wait
        self._order_ack_wait = order_ack_wait
        self._whatif_timeout = whatif_timeout
        self._ib = None
        self._last_error: Optional[str] = None
        self._contract_cache: Dict[str, object] = {}

    # -- connection ------------------------------------------------------- #

    def _client(self):
        if self._ib is None:
            try:
                from ib_async import IB
            except ImportError as exc:  # pragma: no cover - env guard
                raise ImportError(
                    "ib_async is required for IBKRBroker. "
                    "Install it with: pip install ib_async"
                ) from exc
            self._ib = IB()
        return self._ib

    def ensure_connected(self) -> None:
        ib = self._client()
        if ib.isConnected():
            return
        try:
            ib.connect(
                self._host,
                self._port,
                clientId=self._client_id,
                timeout=self._connect_timeout,
            )
            ib.reqMarketDataType(self._market_data_type)
            self._last_error = None
        except Exception as exc:  # noqa: BLE001 - record and re-raise
            self._last_error = str(exc)
            raise

    def _contract(self, symbol: str):
        key = symbol.upper()
        cached = self._contract_cache.get(key)
        if cached is not None:
            return cached
        from ib_async import Stock

        contracts = self._client().qualifyContracts(Stock(key, "SMART", "USD"))
        if not contracts:
            raise ValueError(f"Could not resolve IBKR contract for {symbol!r}")
        self._contract_cache[key] = contracts[0]
        return contracts[0]

    # -- reads ------------------------------------------------------------ #

    def managed_accounts(self) -> List[str]:
        self.ensure_connected()
        return list(self._client().managedAccounts())

    def account_summary(self, account_id: Optional[str] = None) -> List[AccountValue]:
        self.ensure_connected()
        rows = self._client().accountSummary(account_id or "")
        return [AccountValue(tag=r.tag, value=r.value, currency=r.currency) for r in rows]

    def positions(self, account_id: Optional[str] = None) -> List[RawPosition]:
        self.ensure_connected()
        ib = self._client()
        out: List[RawPosition] = []
        # portfolio() carries market price / value / PnL; positions() does not.
        for item in ib.portfolio(account_id or ""):
            c = item.contract
            out.append(
                RawPosition(
                    symbol=c.symbol,
                    conid=c.conId,
                    position=float(item.position),
                    avg_cost=float(item.averageCost),
                    market_price=nan_to_none(item.marketPrice),
                    market_value=nan_to_none(item.marketValue),
                    unrealized_pnl=nan_to_none(item.unrealizedPNL),
                    currency=c.currency,
                )
            )
        return out

    def quote(self, symbol: str) -> Quote:
        self.ensure_connected()
        ib = self._client()
        contract = self._contract(symbol)
        ticker = ib.reqMktData(contract, "", False, False)
        try:
            ib.sleep(self._snapshot_wait)
            return Quote(
                last=nan_to_none(ticker.last),
                bid=nan_to_none(ticker.bid),
                ask=nan_to_none(ticker.ask),
                close=nan_to_none(ticker.close),
            )
        finally:
            ib.cancelMktData(contract)

    # -- orders ----------------------------------------------------------- #

    def _order_obj(
        self,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float],
        time_in_force: str,
        account: Optional[str],
    ):
        from ib_async import LimitOrder, MarketOrder

        action = "BUY" if side.upper() == "BUY" else "SELL"
        tif = (time_in_force or "day").upper()
        qty = int(quantity)
        if order_type.lower() == "limit":
            if limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            order = LimitOrder(action, qty, float(limit_price))
        else:
            order = MarketOrder(action, qty)
        order.tif = tif
        if account:
            order.account = account
        return order

    def _trade_to_raw(self, trade) -> RawOrder:
        o = trade.order
        st = trade.orderStatus
        c = trade.contract
        order_id = str(o.permId or o.orderId)
        otype = "limit" if str(o.orderType).upper() in ("LMT", "LIMIT") else "market"
        return RawOrder(
            order_id=order_id,
            symbol=c.symbol,
            side=o.action,
            order_type=otype,
            quantity=float(o.totalQuantity),
            status=st.status,
            filled_qty=float(st.filled or 0),
            avg_fill_price=nan_to_none(st.avgFillPrice),
            limit_price=nan_to_none(getattr(o, "lmtPrice", None)),
            time_in_force=o.tif,
            conid=c.conId or None,
        )

    def what_if(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> WhatIfResult:
        self.ensure_connected()
        ib = self._client()
        contract = self._contract(symbol)
        order = self._order_obj(side, quantity, order_type, limit_price, time_in_force, account)
        # whatIfOrder blocks until TWS replies; if 'Read-Only API' is enabled (or
        # the API is unresponsive) the reply never comes, so bound it with a
        # timeout and surface a clear, actionable error instead of hanging.
        import asyncio

        from ib_async import util

        try:
            state = util.run(
                asyncio.wait_for(ib.whatIfOrderAsync(contract, order), self._whatif_timeout)
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            self._last_error = "whatIf timed out"
            raise TimeoutError(
                "whatIf preview timed out — in TWS/Gateway open "
                "Global Configuration → API → Settings and DISABLE 'Read-Only API', "
                "then reconnect."
            ) from exc
        return WhatIfResult(
            init_margin=nan_to_none(getattr(state, "initMarginChange", None)),
            maint_margin=nan_to_none(getattr(state, "maintMarginChange", None)),
            commission=nan_to_none(getattr(state, "commission", None)),
            equity_with_loan=nan_to_none(getattr(state, "equityWithLoanChange", None)),
            warning=getattr(state, "warningText", None) or None,
        )

    def place(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> RawOrder:
        self.ensure_connected()
        ib = self._client()
        contract = self._contract(symbol)
        order = self._order_obj(side, quantity, order_type, limit_price, time_in_force, account)
        trade = ib.placeOrder(contract, order)
        ib.sleep(self._order_ack_wait)  # let the initial ack / status arrive
        return self._trade_to_raw(trade)

    def cancel(self, order_id: str) -> bool:
        self.ensure_connected()
        ib = self._client()
        for trade in ib.openTrades():
            if str(trade.order.permId or trade.order.orderId) == str(order_id):
                ib.cancelOrder(trade.order)
                return True
        return False

    def order(self, order_id: str) -> Optional[RawOrder]:
        self.ensure_connected()
        ib = self._client()
        for trade in ib.trades():
            if str(trade.order.permId or trade.order.orderId) == str(order_id):
                return self._trade_to_raw(trade)
        return None

    def open_orders(self) -> List[RawOrder]:
        self.ensure_connected()
        ib = self._client()
        ib.reqOpenOrders()
        ib.sleep(0.2)
        return [self._trade_to_raw(t) for t in ib.openTrades()]

    def recent_orders(self, limit: int = 100) -> List[RawOrder]:
        self.ensure_connected()
        ib = self._client()
        return [self._trade_to_raw(t) for t in ib.trades()[-limit:]]

    def health(self) -> dict:
        ib = self._ib
        connected = bool(ib and ib.isConnected())
        accounts = list(ib.managedAccounts()) if connected else []
        return {
            "gateway_online": connected,
            "accounts": accounts,
            "last_error": self._last_error,
        }


class RedisIBKRConnection:
    """IBKRConnection that proxies every call to the single connector over Redis.

    Used by web processes (FastAPI / Celery) so they never open a socket: each
    method RPUSHes a Command onto the connector's queue and BLPOPs the
    per-command reply. Reads and orders both go through the connector, which
    owns the only ``ib_async`` connection. See :mod:`tradingbot.broker.ibkr_commands`.
    """

    def __init__(
        self,
        redis_client,
        *,
        cmd_queue: str = "ibkr:commands",
        reply_prefix: str = "ibkr:reply:",
        timeout: float = 15.0,
    ):
        self._redis = redis_client
        self._queue = cmd_queue
        self._reply_prefix = reply_prefix
        self._timeout = timeout

    def _call(self, method: str, **params):
        from uuid import uuid4

        # Lazy import keeps module load one-directional (ibkr_commands imports us).
        from .ibkr_commands import (
            Command,
            IBKRConnectorTimeout,
            IBKRConnectorError,
            Response,
            decode_result,
        )

        clean = {k: v for k, v in params.items() if v is not None}
        command = Command(id=uuid4().hex, method=method, params=clean)
        reply_key = self._reply_prefix + command.id
        self._redis.rpush(self._queue, command.to_json())
        popped = self._redis.blpop(reply_key, timeout=max(1, int(self._timeout)))
        if not popped:
            raise IBKRConnectorTimeout(
                f"timed out waiting for connector reply to {method!r}"
            )
        _, raw = popped
        response = Response.from_json(raw)
        if not response.ok:
            raise IBKRConnectorError(response.error or f"{method} failed")
        return decode_result(method, response.result)

    def ensure_connected(self) -> None:
        self._call("ensure_connected")

    def managed_accounts(self) -> List[str]:
        return self._call("managed_accounts")

    def account_summary(self, account_id: Optional[str] = None) -> List[AccountValue]:
        return self._call("account_summary", account_id=account_id)

    def positions(self, account_id: Optional[str] = None) -> List[RawPosition]:
        return self._call("positions", account_id=account_id)

    def quote(self, symbol: str) -> Quote:
        return self._call("quote", symbol=symbol)

    def what_if(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> WhatIfResult:
        return self._call(
            "what_if",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=account,
        )

    def place(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        account: Optional[str] = None,
    ) -> RawOrder:
        return self._call(
            "place",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=account,
        )

    def cancel(self, order_id: str) -> bool:
        return self._call("cancel", order_id=order_id)

    def order(self, order_id: str) -> Optional[RawOrder]:
        return self._call("order", order_id=order_id)

    def open_orders(self) -> List[RawOrder]:
        return self._call("open_orders")

    def recent_orders(self, limit: int = 100) -> List[RawOrder]:
        return self._call("recent_orders", limit=limit)

    def health(self) -> dict:
        return self._call("health")
