"""Unit tests for broker selection via build_broker()."""

from __future__ import annotations

import pytest

from tradingbot.broker.factory import build_broker
from tradingbot.broker.ibkr import IBKRBroker
from tradingbot.broker.ibkr_connection import LocalIBKRConnection
from tradingbot.broker.mock import MockBroker

pytestmark = pytest.mark.unit


def test_mock_is_default():
    assert isinstance(build_broker({}), MockBroker)


def test_alpaca_selected():
    from tradingbot.broker.alpaca import AlpacaBroker

    broker = build_broker(
        {
            "broker": "alpaca",
            "alpaca_api_key": "k",
            "alpaca_api_secret": "s",
            "paper_trading": True,
        }
    )
    assert isinstance(broker, AlpacaBroker)


def test_ibkr_local_builds_local_connection():
    broker = build_broker(
        {
            "broker": "ibkr",
            "ibkr_account_id": "DU1",
            "paper_trading": True,
            "ibkr_host": "h",
            "ibkr_port": 4002,
            "ibkr_client_id": 7,
            "ibkr_market_data_type": 1,
        },
        mode="local",
    )
    assert isinstance(broker, IBKRBroker)
    assert isinstance(broker._conn, LocalIBKRConnection)
    assert broker._account_id == "DU1"
    assert broker._paper is True
    assert broker._conn._port == 4002
    assert broker._conn._client_id == 7
    assert broker._conn._market_data_type == 1


def test_ibkr_blank_account_becomes_none():
    broker = build_broker({"broker": "ibkr", "ibkr_account_id": ""}, mode="local")
    assert broker._account_id is None


def test_ibkr_server_mode_requires_redis_client():
    with pytest.raises(ValueError):
        build_broker({"broker": "ibkr"}, mode="server")


def test_ibkr_server_mode_builds_redis_connection():
    from tradingbot.broker.ibkr_connection import RedisIBKRConnection

    broker = build_broker(
        {"broker": "ibkr", "redis_client": object(), "ibkr_account_id": "DU9"},
        mode="server",
    )
    assert isinstance(broker, IBKRBroker)
    assert isinstance(broker._conn, RedisIBKRConnection)
    assert broker._account_id == "DU9"


def test_unknown_broker_raises():
    with pytest.raises(ValueError):
        build_broker({"broker": "nope"})
