"""Unit tests for RedisIBKRConnection (the web-process proxy) end-to-end.

A loopback fake Redis runs dispatch_command inline on RPUSH, so the full
client -> command -> dispatch -> response -> decode round trip is exercised
without a real connector or Redis.
"""

from __future__ import annotations

import pytest

from tradingbot.broker.ibkr_commands import (
    Command,
    IBKRConnectorError,
    IBKRConnectorTimeout,
    Response,
    dispatch_command,
)
from tradingbot.broker.ibkr_connection import (
    AccountValue,
    Quote,
    RawPosition,
    RedisIBKRConnection,
)
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


class LoopbackRedis:
    """Minimal Redis stand-in: RPUSH to the command queue dispatches inline."""

    def __init__(self, conn, queue="ibkr:commands", reply_prefix="ibkr:reply:"):
        self._conn = conn
        self._queue = queue
        self._reply_prefix = reply_prefix
        self._store: dict[str, list] = {}

    def rpush(self, key, value):
        if key == self._queue:
            command = Command.from_json(value)
            response = dispatch_command(self._conn, command)
            self._store.setdefault(self._reply_prefix + command.id, []).append(
                response.to_json()
            )
        else:
            self._store.setdefault(key, []).append(value)

    def blpop(self, key, timeout=0):
        items = self._store.get(key)
        if items:
            return (key, items.pop(0))
        return None

    def expire(self, key, ttl):  # noqa: D401 - no-op for tests
        return True


def _redis_conn(**fake_kwargs):
    fake = FakeIBKRConnection(**fake_kwargs)
    return RedisIBKRConnection(LoopbackRedis(fake)), fake


def test_account_summary_roundtrip():
    conn, _ = _redis_conn(summary=[AccountValue("NetLiquidation", "1000337", "HKD")])
    rows = conn.account_summary()
    assert rows[0].tag == "NetLiquidation"
    assert rows[0].currency == "HKD"


def test_positions_roundtrip():
    conn, _ = _redis_conn(
        positions=[RawPosition(symbol="NVDA", conid=4815747, position=10, avg_cost=212.4)]
    )
    pos = conn.positions()
    assert pos[0].symbol == "NVDA"
    assert pos[0].position == 10


def test_quote_roundtrip():
    conn, _ = _redis_conn(quote=Quote(last=311.25, bid=311.2, ask=311.3))
    q = conn.quote("AAPL")
    assert q.last == 311.25


def test_place_roundtrip_and_reaches_connection():
    conn, fake = _redis_conn()
    raw = conn.place(symbol="AAPL", side="BUY", quantity=5, order_type="market")
    assert raw.symbol == "AAPL"
    assert raw.quantity == 5
    assert fake.place_calls == 1


def test_error_from_connector_raises():
    conn, _ = _redis_conn(place_raises=RuntimeError("rejected"))
    with pytest.raises(IBKRConnectorError):
        conn.place(symbol="AAPL", side="BUY", quantity=1, order_type="market")


class _SilentRedis:
    """Never returns a reply -> exercises the timeout path."""

    def rpush(self, key, value):
        return 1

    def blpop(self, key, timeout=0):
        return None

    def expire(self, key, ttl):
        return True


def test_timeout_when_no_reply():
    conn = RedisIBKRConnection(_SilentRedis(), timeout=1)
    with pytest.raises(IBKRConnectorTimeout):
        conn.account_summary()
