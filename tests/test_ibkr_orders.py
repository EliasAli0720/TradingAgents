"""Unit tests for IBKRBroker order placement mapping (Phase 2).

Exercised through the shared FakeIBKRConnection — no ib_async / live gateway.
"""

from __future__ import annotations

import pytest

from tradingbot.broker.base import OrderSide, OrderStatus, OrderType
from tradingbot.broker.ibkr import IBKRBroker, _to_order_status
from tradingbot.broker.ibkr_connection import LocalIBKRConnection, RawOrder, WhatIfResult
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# whatIf preview                                                              #
# --------------------------------------------------------------------------- #


def test_preview_returns_whatif_fields():
    conn = FakeIBKRConnection(
        whatif=WhatIfResult(init_margin=1500.0, commission=1.25, warning="size")
    )
    out = IBKRBroker(conn).preview_order("AAPL", 10, OrderSide.BUY)
    assert out["init_margin"] == 1500.0
    assert out["commission"] == 1.25
    assert out["warning"] == "size"
    assert conn.whatif_calls == 1


def test_preview_limit_requires_price():
    with pytest.raises(ValueError):
        IBKRBroker(FakeIBKRConnection()).preview_order(
            "AAPL", 10, OrderSide.BUY, OrderType.LIMIT
        )


# --------------------------------------------------------------------------- #
# submit_order                                                                #
# --------------------------------------------------------------------------- #


def test_submit_market_order_maps_to_pending():
    conn = FakeIBKRConnection()
    order = IBKRBroker(conn).submit_order("aapl", 10, OrderSide.BUY)
    assert conn.place_calls == 1
    assert order.ticker == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.qty == 10
    assert order.status == OrderStatus.PENDING


def test_submit_limit_requires_price():
    conn = FakeIBKRConnection()
    with pytest.raises(ValueError):
        IBKRBroker(conn).submit_order("AAPL", 10, OrderSide.BUY, OrderType.LIMIT)
    assert conn.place_calls == 0


def test_submit_truncates_to_whole_shares():
    conn = FakeIBKRConnection()
    order = IBKRBroker(conn).submit_order("AAPL", 5.9, OrderSide.BUY)
    assert order.qty == 5  # int(5.9)


def test_submit_rejects_sub_one_share():
    conn = FakeIBKRConnection()
    with pytest.raises(ValueError):
        IBKRBroker(conn).submit_order("AAPL", 0.4, OrderSide.BUY)
    assert conn.place_calls == 0


def test_submit_does_not_retry_on_failure():
    conn = FakeIBKRConnection(place_raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        IBKRBroker(conn).submit_order("AAPL", 10, OrderSide.BUY)
    assert conn.place_calls == 1  # exactly once, never retried


# --------------------------------------------------------------------------- #
# get / cancel / history                                                      #
# --------------------------------------------------------------------------- #


def test_get_order_roundtrip_and_missing():
    conn = FakeIBKRConnection()
    broker = IBKRBroker(conn)
    placed = broker.submit_order("AAPL", 3, OrderSide.SELL)
    fetched = broker.get_order(placed.order_id)
    assert fetched.order_id == placed.order_id
    assert fetched.side == OrderSide.SELL
    with pytest.raises(ValueError):
        broker.get_order("does-not-exist")


def test_cancel_known_and_unknown():
    conn = FakeIBKRConnection()
    broker = IBKRBroker(conn)
    placed = broker.submit_order("AAPL", 1, OrderSide.BUY)
    assert broker.cancel_order(placed.order_id) is True
    assert broker.cancel_order("nope") is False


def test_local_cancel_matches_original_order_id_after_perm_id_arrives():
    class Order:
        orderId = 17
        permId = 9001

    class Trade:
        order = Order()

    class FakeIB:
        def __init__(self):
            self.cancelled = []

        def isConnected(self):
            return True

        def openTrades(self):
            return [Trade()]

        def cancelOrder(self, order):
            self.cancelled.append(order)

    ib = FakeIB()
    conn = LocalIBKRConnection()
    conn._ib = ib

    assert conn.cancel("17") is True
    assert ib.cancelled == [Trade.order]


def test_order_history_newest_first():
    conn = FakeIBKRConnection()
    broker = IBKRBroker(conn)
    o1 = broker.submit_order("AAPL", 1, OrderSide.BUY)
    o2 = broker.submit_order("NVDA", 1, OrderSide.BUY)
    history = broker.get_order_history()
    assert [h.order_id for h in history] == [o2.order_id, o1.order_id]


# --------------------------------------------------------------------------- #
# status mapping                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "ibkr_status,filled,qty,expected",
    [
        ("Submitted", 0, 10, OrderStatus.PENDING),
        ("PreSubmitted", 0, 10, OrderStatus.PENDING),
        ("Submitted", 4, 10, OrderStatus.PARTIALLY_FILLED),
        ("Filled", 10, 10, OrderStatus.FILLED),
        ("Cancelled", 0, 10, OrderStatus.CANCELLED),
        ("ApiCancelled", 0, 10, OrderStatus.CANCELLED),
        ("Inactive", 0, 10, OrderStatus.REJECTED),
        ("weird-unknown", 0, 10, OrderStatus.PENDING),
    ],
)
def test_status_mapping(ibkr_status, filled, qty, expected):
    assert _to_order_status(ibkr_status, filled, qty) == expected


def test_to_order_partial_fill_via_get_order():
    conn = FakeIBKRConnection()
    # seed a partially filled order directly
    conn._orders["X1"] = RawOrder(
        order_id="X1",
        symbol="AAPL",
        side="BUY",
        order_type="limit",
        quantity=10,
        status="Submitted",
        filled_qty=4,
        avg_fill_price=300.0,
        limit_price=305.0,
    )
    order = IBKRBroker(conn).get_order("X1")
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.order_type == OrderType.LIMIT
    assert order.filled_avg_price == 300.0
    assert order.limit_price == 305.0
