"""Unit tests for the connector command protocol (serialization + dispatch)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradingbot.broker.ibkr_commands import (
    Command,
    Response,
    decode_result,
    dispatch_command,
    encode_result,
)
from tradingbot.broker.ibkr_connection import (
    AccountValue,
    Quote,
    RawOrder,
    RawPosition,
    WhatIfResult,
)
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


def test_command_json_roundtrip():
    cmd = Command(id="abc", method="quote", params={"symbol": "AAPL"})
    assert Command.from_json(cmd.to_json()) == cmd


def test_response_json_roundtrip():
    resp = Response(id="abc", ok=True, result=[1, 2], error=None)
    assert Response.from_json(resp.to_json()) == resp


def test_encode_result_handles_dataclass_and_datetime():
    raw = RawOrder(
        order_id="O1",
        symbol="AAPL",
        side="BUY",
        order_type="market",
        quantity=10,
        status="Submitted",
        submitted_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )
    encoded = encode_result(raw)
    assert encoded["order_id"] == "O1"
    assert isinstance(encoded["submitted_at"], str)  # datetime -> iso string


def test_decode_result_rebuilds_typed_objects():
    av = decode_result("account_summary", [{"tag": "NetLiquidation", "value": "1", "currency": "USD"}])
    assert av == [AccountValue("NetLiquidation", "1", "USD")]

    pos = decode_result("positions", [encode_result(RawPosition("AAPL", 1, 5, 100.0))])
    assert pos[0].symbol == "AAPL" and pos[0].position == 5

    q = decode_result("quote", encode_result(Quote(last=10.0)))
    assert q == Quote(last=10.0)

    wif = decode_result("what_if", encode_result(WhatIfResult(commission=1.0)))
    assert wif.commission == 1.0

    assert decode_result("order", None) is None
    assert decode_result("cancel", True) is True
    assert decode_result("managed_accounts", ["DU1"]) == ["DU1"]


def test_decode_place_parses_submitted_at():
    raw = RawOrder(
        order_id="O1", symbol="AAPL", side="BUY", order_type="market",
        quantity=1, status="Filled",
        submitted_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
    )
    decoded = decode_result("place", encode_result(raw))
    assert isinstance(decoded.submitted_at, datetime)


# --------------------------------------------------------------------------- #
# dispatch_command                                                            #
# --------------------------------------------------------------------------- #


def test_dispatch_account_summary_ok():
    conn = FakeIBKRConnection(summary=[AccountValue("NetLiquidation", "1000", "USD")])
    resp = dispatch_command(conn, Command("1", "account_summary", {}))
    assert resp.ok
    assert decode_result("account_summary", resp.result)[0].tag == "NetLiquidation"


def test_dispatch_place_ok():
    conn = FakeIBKRConnection()
    resp = dispatch_command(
        conn,
        Command("2", "place", {"symbol": "AAPL", "side": "BUY", "quantity": 3, "order_type": "market"}),
    )
    assert resp.ok
    assert conn.place_calls == 1
    assert decode_result("place", resp.result).symbol == "AAPL"


def test_dispatch_unknown_method():
    resp = dispatch_command(FakeIBKRConnection(), Command("3", "frobnicate", {}))
    assert resp.ok is False
    assert "unknown method" in resp.error


def test_dispatch_captures_exception():
    conn = FakeIBKRConnection(place_raises=RuntimeError("boom"))
    resp = dispatch_command(
        conn,
        Command("4", "place", {"symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "market"}),
    )
    assert resp.ok is False
    assert "boom" in resp.error
