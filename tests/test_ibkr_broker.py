"""Unit tests for IBKRBroker read-path mapping (account / positions / price).

These exercise the IBKR -> unified-model mapping through a fake transport, so
they need neither ib_async nor a running TWS/Gateway.
"""

from __future__ import annotations

import pytest

from tradingbot.broker.ibkr import IBKRBroker
from tradingbot.broker.ibkr_connection import (
    AccountValue,
    IBKRConnection,
    Quote,
    RawPosition,
)
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


def test_fake_satisfies_protocol():
    assert isinstance(FakeIBKRConnection(), IBKRConnection)


# --------------------------------------------------------------------------- #
# Account                                                                     #
# --------------------------------------------------------------------------- #


def test_account_maps_standard_tags():
    conn = FakeIBKRConnection(
        summary=[
            AccountValue("NetLiquidation", "1000337.73", "HKD"),
            AccountValue("AvailableFunds", "994760.58", "HKD"),
            AccountValue("BuyingPower", "6631737.22", "HKD"),
            AccountValue("TotalCashValue", "983350.81", "HKD"),
        ]
    )
    acct = IBKRBroker(conn).get_account()
    assert acct.cash == pytest.approx(994760.58)
    assert acct.portfolio_value == pytest.approx(1000337.73)
    assert acct.equity == pytest.approx(1000337.73)
    assert acct.buying_power == pytest.approx(6631737.22)


def test_account_falls_back_when_preferred_tag_missing():
    conn = FakeIBKRConnection(
        summary=[
            AccountValue("NetLiquidation", "500.0"),
            AccountValue("TotalCashValue", "120.0"),  # no AvailableFunds
        ]
    )
    acct = IBKRBroker(conn).get_account()
    assert acct.cash == pytest.approx(120.0)          # fell back to TotalCashValue
    assert acct.buying_power == pytest.approx(0.0)     # no BuyingPower / AvailableFunds


def test_account_handles_unparseable_value():
    conn = FakeIBKRConnection(summary=[AccountValue("NetLiquidation", "")])
    acct = IBKRBroker(conn).get_account()
    assert acct.portfolio_value == 0.0


# --------------------------------------------------------------------------- #
# Positions                                                                   #
# --------------------------------------------------------------------------- #


def test_position_uses_ibkr_market_fields():
    conn = FakeIBKRConnection(
        positions=[
            RawPosition(
                symbol="AAPL",
                conid=265598,
                position=10,
                avg_cost=300.0,
                market_price=311.25,
                market_value=3112.5,
                unrealized_pnl=112.5,
                currency="USD",
            )
        ]
    )
    pos = IBKRBroker(conn).get_positions()
    assert len(pos) == 1
    p = pos[0]
    assert p.ticker == "AAPL"
    assert p.qty == 10
    assert p.current_price == pytest.approx(311.25)
    assert p.market_value == pytest.approx(3112.5)
    assert p.unrealized_pnl == pytest.approx(112.5)
    assert p.unrealized_pnl_pct == pytest.approx(112.5 / 3000.0)
    assert p.side == "long"


def test_position_computes_when_market_fields_missing():
    conn = FakeIBKRConnection(
        positions=[
            RawPosition(symbol="msft", conid=272093, position=4, avg_cost=100.0)
        ]
    )
    p = IBKRBroker(conn).get_positions()[0]
    assert p.ticker == "MSFT"
    assert p.current_price == pytest.approx(100.0)     # falls back to avg cost
    assert p.market_value == pytest.approx(400.0)
    assert p.unrealized_pnl == pytest.approx(0.0)


def test_short_position_side():
    conn = FakeIBKRConnection(
        positions=[RawPosition(symbol="TSLA", conid=1, position=-5, avg_cost=200.0)]
    )
    assert IBKRBroker(conn).get_positions()[0].side == "short"


def test_zero_positions_are_skipped():
    conn = FakeIBKRConnection(
        positions=[
            RawPosition(symbol="AAPL", conid=1, position=0, avg_cost=300.0),
            RawPosition(symbol="NVDA", conid=2, position=3, avg_cost=100.0),
        ]
    )
    tickers = [p.ticker for p in IBKRBroker(conn).get_positions()]
    assert tickers == ["NVDA"]


def test_get_position_match_and_miss():
    conn = FakeIBKRConnection(
        positions=[RawPosition(symbol="AAPL", conid=1, position=2, avg_cost=300.0)]
    )
    broker = IBKRBroker(conn)
    assert broker.get_position("aapl").ticker == "AAPL"
    assert broker.get_position("GOOG") is None


# --------------------------------------------------------------------------- #
# Market data                                                                 #
# --------------------------------------------------------------------------- #


def test_latest_price_prefers_last():
    conn = FakeIBKRConnection(quote=Quote(last=311.25, bid=311.2, ask=311.3, close=312.5))
    assert IBKRBroker(conn).get_latest_price("AAPL") == pytest.approx(311.25)


def test_latest_price_midpoint_when_no_last():
    conn = FakeIBKRConnection(quote=Quote(last=None, bid=10.0, ask=10.4, close=9.5))
    assert IBKRBroker(conn).get_latest_price("AAPL") == pytest.approx(10.2)


def test_latest_price_close_when_no_last_or_quotes():
    conn = FakeIBKRConnection(quote=Quote(last=None, bid=None, ask=None, close=9.5))
    assert IBKRBroker(conn).get_latest_price("AAPL") == pytest.approx(9.5)


def test_latest_price_raises_when_empty():
    conn = FakeIBKRConnection(quote=Quote())
    with pytest.raises(ValueError):
        IBKRBroker(conn).get_latest_price("AAPL")


# --------------------------------------------------------------------------- #
# Health                                                                      #
# --------------------------------------------------------------------------- #


def test_health_includes_account_and_paper_flag():
    broker = IBKRBroker(FakeIBKRConnection(), account_id="DU1", paper=True)
    h = broker.health()
    assert h["account_id"] == "DU1"
    assert h["paper"] is True
    assert "gateway_online" in h
