"""Tests for the real Webull SDK wrapper wiring.

The SDK itself is optional and networked; these tests install tiny fake modules
into ``sys.modules`` so we can verify which SDK surface the wrapper calls.
"""

from __future__ import annotations

import sys
import types

import pytest

from tradingbot.broker.webull_client import SdkWebullClient

pytestmark = pytest.mark.unit


class FakeApiClient:
    instances = []

    def __init__(self, app_key, app_secret, region, connect_timeout=None, timeout=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.region = region
        self.connect_timeout = connect_timeout
        self.read_timeout = timeout
        self.endpoints = []
        self.tokens = []
        FakeApiClient.instances.append(self)

    def add_endpoint(self, region, endpoint):
        self.endpoints.append((region, endpoint))

    def set_token(self, token):
        self.tokens.append(token)


class FakeAccountV2:
    def get_account_list(self):
        return [{"account_id": "DUV2"}]

    def get_account_balance(self, account_id):
        return {"total_cash": "10", "net_liquidation_value": "20", "buying_power": "30"}

    def get_account_position(self, account_id):
        return [{"symbol": "AAPL", "quantity": "1"}]


class FakeOrderV2:
    def preview_order(self, account_id, orders):
        return {"estimated_cost": "100", "orders": orders}

    def place_order(self, account_id, orders):
        return {"client_order_id": orders[0]["client_order_id"], "status": "Submitted"}

    def cancel_order(self, account_id, order_id):
        return {"success": True}

    def get_order_detail(self, account_id, order_id):
        return {"client_order_id": order_id, "status": "Filled"}

    def get_order_open(self, account_id, page_size=None):
        return [{"client_order_id": "open-1"}]


class FakeTradeClient:
    def __init__(self, api_client):
        self.api_client = api_client
        self.account_v2 = FakeAccountV2()
        self.order_v2 = FakeOrderV2()


class FakeInstrument:
    def get_instrument(self, symbols=None, category=None):
        return [{"instrument_id": "iid-1", "symbol": symbols, "category": category}]


class FakeMarketData:
    def get_quotes(self, symbol, category):
        return {"last": "123.45", "symbol": symbol, "category": category}


class FakeDataClient:
    def __init__(self, api_client):
        self.api_client = api_client
        self.instrument = FakeInstrument()
        self.market_data = FakeMarketData()


@pytest.fixture()
def fake_webull_v2(monkeypatch):
    FakeApiClient.instances = []
    modules = {
        "webull": types.ModuleType("webull"),
        "webull.core": types.ModuleType("webull.core"),
        "webull.core.client": types.ModuleType("webull.core.client"),
        "webull.trade": types.ModuleType("webull.trade"),
        "webull.trade.trade_client": types.ModuleType("webull.trade.trade_client"),
        "webull.data": types.ModuleType("webull.data"),
        "webull.data.data_client": types.ModuleType("webull.data.data_client"),
    }
    modules["webull.core.client"].ApiClient = FakeApiClient
    modules["webull.trade.trade_client"].TradeClient = FakeTradeClient
    modules["webull.data.data_client"].DataClient = FakeDataClient
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return FakeApiClient


def test_api_key_mode_uses_v2_clients_without_token_or_oauth_endpoint(fake_webull_v2):
    client = SdkWebullClient(
        access_token="",
        app_key="app-key",
        app_secret="app-secret",
        auth_type="api_key",
        region="us",
    )

    assert client.health()["accounts"] == ["DUV2"]
    assert client.account_balance("DUV2")["cash"] == "10"
    assert client.positions("DUV2")[0]["ticker"] == "AAPL"
    assert client.resolve_instrument("AAPL") == "iid-1"
    assert client.get_quote("AAPL")["last"] == "123.45"
    assert fake_webull_v2.instances[0].endpoints == []
    assert fake_webull_v2.instances[0].tokens == []


class _FakeResponse:
    """Mimics the ``requests.Response`` the real SDK returns from each call."""

    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_health_unwraps_requests_response_account_list(fake_webull_v2, monkeypatch):
    # Regression: the real SDK returns a requests.Response, not a list/dict.
    # health() must unwrap .json() to find the account ids (previously it read
    # the Response's __dict__ and saw zero accounts → "no Webull account found").
    monkeypatch.setattr(
        FakeAccountV2,
        "get_account_list",
        lambda self: _FakeResponse([{"account_id": "RESP-1"}, {"account_id": "RESP-2"}]),
    )
    client = SdkWebullClient(
        access_token="",
        app_key="app-key",
        app_secret="app-secret",
        auth_type="api_key",
        region="us",
    )

    health = client.health()
    assert health["connected"] is True
    assert health["accounts"] == ["RESP-1", "RESP-2"]


def test_account_balance_flattens_nested_currency_assets(fake_webull_v2, monkeypatch):
    # Webull's real balance response nests figures under account_currency_assets;
    # account_balance must surface them, not return empty/None.
    monkeypatch.setattr(
        FakeAccountV2,
        "get_account_balance",
        lambda self, account_id: _FakeResponse(
            {
                "account_id": account_id,
                "total_asset_currency": "USD",
                "account_currency_assets": [
                    {
                        "currency": "USD",
                        "cash_balance": "1234.56",
                        "net_liquidation_value": "5000.00",
                        "buying_power": "2469.12",
                        "total_market_value": "3765.44",
                    }
                ],
            }
        ),
    )
    client = SdkWebullClient(
        access_token="", app_key="k", app_secret="s", auth_type="api_key", region="us"
    )

    bal = client.account_balance("ACC")
    assert bal["cash"] == "1234.56"
    assert bal["portfolio_value"] == "5000.00"
    assert bal["buying_power"] == "2469.12"
    assert bal["equity"] == "3765.44"


def test_quote_prefers_snapshot_price_list_payload(fake_webull_v2, monkeypatch):
    # Webull's depth quote endpoint may only contain order book levels; proposal
    # sizing needs a tradeable reference price, so use stock snapshot first.
    monkeypatch.setattr(
        FakeMarketData,
        "get_snapshot",
        lambda self, symbols, category, extend_hour_required=None, overnight_required=None: _FakeResponse(
            [
                {
                    "symbol": "MSFT",
                    "price": "421.50",
                    "pre_close": "420.00",
                    "bid_price": "421.40",
                    "ask_price": "421.60",
                }
            ]
        ),
        raising=False,
    )
    client = SdkWebullClient(
        access_token="", app_key="k", app_secret="s", auth_type="api_key", region="us"
    )

    quote = client.get_quote("MSFT")
    assert quote["price"] == "421.50"
    assert quote["close"] == "420.00"
    assert quote["bid"] == "421.40"
    assert quote["ask"] == "421.60"


def test_quote_reads_nested_depth_bid_ask_when_snapshot_has_no_price(fake_webull_v2, monkeypatch):
    # /stock/quotes is a depth endpoint; bid/ask are usually arrays, not
    # top-level scalar fields.
    monkeypatch.setattr(
        FakeMarketData,
        "get_quotes",
        lambda self, symbol, category: _FakeResponse(
            {
                "symbol": symbol,
                "bids": [{"price": "421.00", "size": "100"}],
                "asks": [{"price": "422.00", "size": "100"}],
            }
        ),
    )
    client = SdkWebullClient(
        access_token="", app_key="k", app_secret="s", auth_type="api_key", region="us"
    )

    quote = client.get_quote("MSFT")
    assert quote["bid"] == "421.00"
    assert quote["ask"] == "422.00"


def test_oauth_mode_sets_token_and_endpoint_with_v2_client(fake_webull_v2):
    client = SdkWebullClient(
        access_token="access-token",
        app_key="app-key",
        app_secret="app-secret",
        auth_type="oauth",
        region="us",
        paper=True,
    )

    assert client.health()["connected"] is True
    api = fake_webull_v2.instances[0]
    assert api.endpoints == [("us", "us-oauth-open-api.uat.webullbroker.com")]
    assert api.tokens == ["access-token"]
