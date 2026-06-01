"""Tests for the Webull broker adapter (fake WebullClient — no SDK, no network)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradingbot.broker.base import OrderSide, OrderStatus, OrderType
from tradingbot.broker.webull import WebullBroker


# --------------------------------------------------------------------------- #
# Fake client                                                                 #
# --------------------------------------------------------------------------- #


class FakeWebullClient:
    """In-memory WebullClient that records calls and returns canned shapes."""

    def __init__(self, **overrides):
        self.calls: list[tuple] = []
        self.resolve_count = 0
        self._balance = overrides.get(
            "balance",
            {
                "cash": "10000",
                "portfolio_value": "15000",
                "buying_power": "20000",
                "equity": "15000",
            },
        )
        self._positions = overrides.get(
            "positions",
            [
                {
                    "ticker": "AAPL",
                    "qty": "10",
                    "avg_entry_price": "100",
                    "current_price": "110",
                    "market_value": "1100",
                    "unrealized_pnl": "100",
                    "unrealized_pnl_pct": "0.1",
                }
            ],
        )
        self._quote = overrides.get("quote", {"last": "110.5", "close": "108"})
        self._place_status = overrides.get("place_status", "Filled")

    def account_balance(self, account_id):
        self.calls.append(("account_balance", account_id))
        return dict(self._balance)

    def positions(self, account_id):
        self.calls.append(("positions", account_id))
        return [dict(p) for p in self._positions]

    def resolve_instrument(self, symbol):
        self.resolve_count += 1
        self.calls.append(("resolve_instrument", symbol))
        return f"id-{symbol.upper()}"

    def get_quote(self, symbol):
        self.calls.append(("get_quote", symbol))
        return dict(self._quote)

    def preview_order(self, account_id, payload):
        self.calls.append(("preview_order", account_id, payload))
        return {"est_commission": "1.0", "buying_power": "19000", "warning_text": "ok"}

    def place_order(self, account_id, payload):
        self.calls.append(("place_order", account_id, payload))
        return {
            "order_id": "WB-1",
            "client_order_id": payload["client_order_id"],
            "ticker": "AAPL",
            "side": payload["side"],
            "order_type": payload["order_type"],
            "qty": payload["qty"],
            "status": self._place_status,
            "filled_qty": payload["qty"] if self._place_status == "Filled" else "0",
            "filled_avg_price": "105" if self._place_status == "Filled" else None,
            "limit_price": payload.get("limit_price"),
        }

    def cancel_order(self, account_id, order_id):
        self.calls.append(("cancel_order", account_id, order_id))
        return True

    def get_order(self, account_id, order_id):
        self.calls.append(("get_order", account_id, order_id))
        if order_id == "missing":
            return None
        return {"order_id": order_id, "ticker": "AAPL", "side": "BUY",
                "order_type": "MARKET", "qty": "10", "status": "Working"}

    def list_orders(self, account_id, limit=100):
        self.calls.append(("list_orders", account_id, limit))
        return [
            {"order_id": "old", "ticker": "AAPL", "side": "BUY",
             "order_type": "MARKET", "qty": "5", "status": "Filled"},
            {"order_id": "new", "ticker": "MSFT", "side": "SELL",
             "order_type": "LIMIT", "qty": "3", "status": "Cancelled"},
        ]

    def health(self):
        self.calls.append(("health",))
        return {"connected": True, "accounts": ["DU999"], "last_error": None}


def _broker(**overrides) -> WebullBroker:
    return WebullBroker(FakeWebullClient(**overrides), account_id="DU999", region="us")


# --------------------------------------------------------------------------- #
# Account / positions                                                         #
# --------------------------------------------------------------------------- #


def test_get_account_coerces_strings():
    acct = _broker().get_account()
    assert acct.cash == 10000.0
    assert acct.portfolio_value == 15000.0
    assert acct.buying_power == 20000.0
    assert acct.equity == 15000.0


def test_get_account_equity_falls_back_to_net_liq():
    broker = _broker(balance={"cash": "5", "portfolio_value": "100", "buying_power": "9"})
    assert broker.get_account().equity == 100.0


def test_get_positions_maps_fields():
    pos = _broker().get_positions()
    assert len(pos) == 1
    p = pos[0]
    assert p.ticker == "AAPL"
    assert p.qty == 10.0
    assert p.current_price == 110.0
    assert p.unrealized_pnl == 100.0
    assert p.side == "long"


def test_get_position_filters_by_ticker():
    broker = _broker()
    assert broker.get_position("aapl").ticker == "AAPL"
    assert broker.get_position("TSLA") is None


def test_position_pct_derived_when_absent():
    broker = _broker(
        positions=[{"ticker": "X", "qty": "10", "avg_entry_price": "100",
                    "current_price": "120", "unrealized_pnl": "200"}]
    )
    p = broker.get_positions()[0]
    assert p.unrealized_pnl_pct == pytest.approx(0.2)  # 200 / (100*10)
    assert p.market_value == pytest.approx(1200.0)     # qty * current


# --------------------------------------------------------------------------- #
# Instrument resolution + caching                                             #
# --------------------------------------------------------------------------- #


def test_instrument_resolution_is_cached():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="DU999")
    broker.submit_order("AAPL", 1, OrderSide.BUY)
    broker.submit_order("AAPL", 2, OrderSide.BUY)
    broker.preview_order("AAPL", 3, OrderSide.BUY)
    assert client.resolve_count == 1  # resolved once, reused thereafter


def test_unresolvable_instrument_raises():
    class NoInstrument(FakeWebullClient):
        def resolve_instrument(self, symbol):
            return ""

    broker = WebullBroker(NoInstrument(), account_id="DU999")
    with pytest.raises(ValueError, match="Could not resolve Webull instrument"):
        broker.submit_order("ZZZZ", 1, OrderSide.BUY)


# --------------------------------------------------------------------------- #
# Orders                                                                       #
# --------------------------------------------------------------------------- #


def test_limit_order_requires_price():
    broker = _broker()
    with pytest.raises(ValueError, match="limit_price is required"):
        broker.submit_order("AAPL", 10, OrderSide.BUY, OrderType.LIMIT)


def test_submit_order_builds_payload_and_maps():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="DU999")
    order = broker.submit_order("AAPL", 10, OrderSide.BUY, OrderType.MARKET)
    place = [c for c in client.calls if c[0] == "place_order"][0]
    payload = place[2]
    assert payload["instrument_id"] == "id-AAPL"
    assert payload["side"] == "BUY"
    assert payload["order_type"] == "MARKET"
    assert payload["tif"] == "DAY"
    assert payload["client_order_id"]  # auto-generated idempotency key
    # market is required by the SDK (builds the "<market>_STOCK" category header);
    # extended_hours_trading must be present (false for market orders).
    assert payload["market"] == "US"
    assert payload["extended_hours_trading"] is False
    assert payload["combo_type"] == "NORMAL"
    assert payload["symbol"] == "AAPL"
    assert payload["instrument_type"] == "EQUITY"
    assert payload["quantity"] == "10"
    assert payload["entrust_type"] == "QTY"
    assert payload["time_in_force"] == "DAY"
    assert payload["support_trading_session"] == "CORE"
    assert order.status == OrderStatus.FILLED
    assert order.filled_avg_price == 105.0
    assert order.ticker == "AAPL"


def test_submit_order_uses_supplied_client_order_id():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="DU999")
    broker.submit_order("AAPL", 1, OrderSide.BUY, client_order_id="approval-42")
    payload = [c for c in client.calls if c[0] == "place_order"][0][2]
    assert payload["client_order_id"] == "approval-42"


def test_limit_payload_includes_price():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="DU999")
    broker.submit_order("AAPL", 1, OrderSide.SELL, OrderType.LIMIT, limit_price=200.0)
    payload = [c for c in client.calls if c[0] == "place_order"][0][2]
    assert payload["side"] == "SELL"
    assert payload["order_type"] == "LIMIT"
    assert payload["limit_price"] == "200.0"


def test_partial_fill_downgrades_filled_status():
    class PartialClient(FakeWebullClient):
        def place_order(self, account_id, payload):
            return {"order_id": "P1", "ticker": "AAPL", "side": "BUY",
                    "order_type": "MARKET", "qty": "10", "status": "Filled",
                    "filled_qty": "4"}

    broker = WebullBroker(PartialClient(), account_id="DU999")
    order = broker.submit_order("AAPL", 10, OrderSide.BUY)
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_qty == 4.0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Filled", OrderStatus.FILLED),
        ("PartiallyFilled", OrderStatus.PARTIALLY_FILLED),
        ("Cancelled", OrderStatus.CANCELLED),
        ("Canceled", OrderStatus.CANCELLED),
        ("Working", OrderStatus.PENDING),
        ("Pending", OrderStatus.PENDING),
        ("Rejected", OrderStatus.REJECTED),
        ("Failed", OrderStatus.REJECTED),
        ("Expired", OrderStatus.EXPIRED),
        ("Mystery", OrderStatus.PENDING),
    ],
)
def test_status_mapping(raw, expected):
    order = WebullBroker._to_order({"order_id": "1", "qty": "1", "status": raw})
    assert order.status == expected


def test_get_order_missing_raises():
    broker = _broker()
    with pytest.raises(ValueError, match="not found"):
        broker.get_order("missing")


def test_get_order_history_is_newest_first():
    history = _broker().get_order_history()
    assert [o.order_id for o in history] == ["new", "old"]


def test_cancel_order_swallows_errors():
    class BoomClient(FakeWebullClient):
        def cancel_order(self, account_id, order_id):
            raise RuntimeError("boom")

    broker = WebullBroker(BoomClient(), account_id="DU999")
    assert broker.cancel_order("x") is False


# --------------------------------------------------------------------------- #
# Preview / quote / health                                                    #
# --------------------------------------------------------------------------- #


def test_preview_order_normalises_shape():
    out = _broker().preview_order("AAPL", 10, OrderSide.BUY)
    assert out["commission"] == 1.0
    assert out["buying_power"] == 19000.0
    assert out["warning"] == "ok"
    assert "init_margin" in out


def test_preview_order_builds_webull_required_stock_fields():
    client = FakeWebullClient()
    broker = WebullBroker(client, account_id="DU999")
    broker.preview_order("AAPL", 1, OrderSide.BUY)

    payload = [c for c in client.calls if c[0] == "preview_order"][0][2]
    assert payload["combo_type"] == "NORMAL"
    assert payload["symbol"] == "AAPL"
    assert payload["instrument_type"] == "EQUITY"
    assert payload["quantity"] == "1"
    assert payload["entrust_type"] == "QTY"
    assert payload["time_in_force"] == "DAY"
    assert payload["support_trading_session"] == "CORE"


def test_get_latest_price_prefers_last():
    assert _broker().get_latest_price("AAPL") == 110.5


def test_get_latest_price_no_data_raises():
    broker = _broker(quote={})
    with pytest.raises(ValueError, match="No price available"):
        broker.get_latest_price("AAPL")


def test_health_maps_connected():
    h = _broker().health()
    assert h["gateway_online"] is True
    assert h["accounts"] == ["DU999"]


def test_health_reports_client_failure():
    class BoomClient(FakeWebullClient):
        def health(self):
            raise RuntimeError("token expired")

    h = WebullBroker(BoomClient(), account_id="DU999").health()
    assert h["gateway_online"] is False
    assert "token expired" in h["last_error"]


def test_to_order_defaults_submitted_at():
    order = WebullBroker._to_order({"order_id": "1", "qty": "1", "status": "Working"})
    assert isinstance(order.submitted_at, datetime)
    assert order.submitted_at.tzinfo == timezone.utc
