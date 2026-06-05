"""Sidecar smoke: token gate + connect/read against the mock broker (no TWS)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

TOKEN = "test-sidecar-token"
AUTH = {"authorization": f"Bearer {TOKEN}"}


def _client() -> TestClient:
    os.environ["SIDECAR_TOKEN"] = TOKEN
    from tradingbot.sidecar.app import app

    return TestClient(app)


def test_ping_is_unauthenticated() -> None:
    assert _client().get("/ping").json() == {"ok": True}


def test_endpoints_require_token() -> None:
    c = _client()
    assert c.get("/health").status_code == 401
    assert c.get("/account").status_code == 401
    assert c.get("/health", headers={"authorization": "Bearer wrong"}).status_code == 401


def test_health_before_connect_reports_disconnected() -> None:
    c = _client()
    c.post("/disconnect", headers=AUTH)  # ensure a clean slate
    body = c.get("/health", headers=AUTH).json()
    assert body["connected"] is False
    assert body["gateway_online"] is False


def test_connect_mock_then_read_account_positions_orders() -> None:
    c = _client()
    r = c.post("/connect", json={"broker": "mock", "paper": True}, headers=AUTH)
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["broker"] == "mock"
    assert status["connected"] is True

    account = c.get("/account", headers=AUTH)
    assert account.status_code == 200
    assert set(account.json()) >= {"cash", "portfolio_value", "buying_power", "equity"}

    assert c.get("/positions", headers=AUTH).status_code == 200
    assert isinstance(c.get("/positions", headers=AUTH).json(), list)
    assert c.get("/orders", headers=AUTH).status_code == 200

    c.post("/disconnect", headers=AUTH)


def test_discover_requires_token() -> None:
    assert _client().post("/discover", json={}).status_code == 401


def test_discover_lists_open_ports(monkeypatch) -> None:
    import tradingbot.sidecar.app as appmod

    # Simulate a paper TWS (7497) + paper Gateway (4002) listening, live ports closed.
    monkeypatch.setattr(appmod, "_port_open", lambda host, port, timeout=0.35: port in (7497, 4002))
    c = _client()
    body = c.post("/discover", json={}, headers=AUTH).json()
    by_port = {cand["port"]: cand for cand in body["candidates"]}
    assert set(by_port) == {7497, 4002}
    assert by_port[7497]["kind"] == "tws" and by_port[7497]["paper"] is True
    assert by_port[4002]["kind"] == "gateway" and by_port[4002]["paper"] is True


def test_infer_paper_from_account_prefix() -> None:
    from tradingbot.sidecar.app import _infer_paper

    assert _infer_paper("DU441028", False) is True   # DU… = paper, overrides hint
    assert _infer_paper("U1234567", True) is False    # U… = live, overrides hint
    assert _infer_paper("F1234567", True) is False
    assert _infer_paper(None, True) is True           # unknown → fall back to hint
    assert _infer_paper("X999", True) is True          # unrecognised → fall back


def test_connect_auto_adopts_logged_in_account(monkeypatch) -> None:
    """One-click connect with no account_id: adopt the managed account IBKR
    reports, and derive paper/live from its prefix (here DU… ⇒ paper)."""
    import tradingbot.sidecar.app as appmod

    class FakeConn:
        def ensure_connected(self):
            pass

        def managed_accounts(self):
            return ["DU441028"]

        def health(self):
            return {"gateway_online": True, "accounts": ["DU441028"], "last_error": None}

    class FakeBroker:
        def __init__(self):
            self._conn = FakeConn()

        def health(self):
            return self._conn.health()

    monkeypatch.setattr(appmod, "BUILD_BROKER", lambda cfg, mode="local": FakeBroker())
    c = _client()
    status = c.post("/connect", json={"broker": "ibkr", "paper": False}, headers=AUTH).json()
    assert status["account_id"] == "DU441028"
    assert status["accounts"] == ["DU441028"]
    assert status["paper"] is True  # DU prefix wins over the paper=False hint
    c.post("/disconnect", headers=AUTH)


def test_account_and_positions_can_target_selected_account(monkeypatch) -> None:
    """The desktop UI can select any managed IBKR account; sidecar reads must
    use that account instead of the one originally adopted on connect."""
    import tradingbot.sidecar.app as appmod
    from tradingbot.broker.ibkr_connection import AccountValue, RawPosition

    class FakeConn:
        def __init__(self):
            self.summary_accounts = []
            self.position_accounts = []

        def ensure_connected(self):
            pass

        def managed_accounts(self):
            return ["DUPRIMARY", "DUSECOND"]

        def health(self):
            return {
                "gateway_online": True,
                "accounts": ["DUPRIMARY", "DUSECOND"],
                "last_error": None,
            }

        def account_summary(self, account_id=None):
            self.summary_accounts.append(account_id)
            return [
                AccountValue("AvailableFunds", "2000", "USD"),
                AccountValue("NetLiquidation", "2000", "USD"),
                AccountValue("BuyingPower", "8000", "USD"),
                AccountValue("TotalCashValue", "2000", "USD"),
            ]

        def positions(self, account_id=None):
            self.position_accounts.append(account_id)
            return [
                RawPosition(
                    symbol="MSFT",
                    conid=123,
                    position=2,
                    avg_cost=100.0,
                    market_price=110.0,
                    market_value=220.0,
                    unrealized_pnl=20.0,
                )
            ]

    created = {}

    def build_broker(_cfg, mode="local"):
        from tradingbot.broker.ibkr import IBKRBroker

        conn = FakeConn()
        created["conn"] = conn
        return IBKRBroker(conn, account_id=None)

    monkeypatch.setattr(appmod, "BUILD_BROKER", build_broker)
    c = _client()
    status = c.post("/connect", json={"broker": "ibkr"}, headers=AUTH).json()
    assert status["accounts"] == ["DUPRIMARY", "DUSECOND"]

    account = c.get("/account", params={"account_id": "DUSECOND"}, headers=AUTH)
    assert account.status_code == 200, account.text
    positions = c.get("/positions", params={"account_id": "DUSECOND"}, headers=AUTH)
    assert positions.status_code == 200, positions.text

    assert created["conn"].summary_accounts == ["DUSECOND"]
    assert created["conn"].position_accounts == ["DUSECOND"]
    c.post("/disconnect", headers=AUTH)


def test_account_without_connection_is_409() -> None:
    c = _client()
    c.post("/disconnect", headers=AUTH)
    assert c.get("/account", headers=AUTH).status_code == 409


def test_execute_quote_cancel_via_injected_broker(monkeypatch) -> None:
    """Exercise the execution passthrough without yfinance/TWS by injecting a
    deterministic in-memory broker through the BUILD_BROKER hook."""
    from datetime import datetime

    import tradingbot.sidecar.app as appmod
    from tradingbot.broker.base import (
        AccountInfo,
        Order,
        OrderStatus,
        OrderType,
    )

    class FakeBroker:
        def get_account(self):
            return AccountInfo(cash=1.0, portfolio_value=1.0, buying_power=1.0, equity=1.0)

        def get_positions(self):
            return []

        def get_order_history(self, limit: int = 100):
            return []

        def get_latest_price(self, ticker: str) -> float:
            return 123.0

        def submit_order(self, ticker, qty, side, order_type=OrderType.MARKET,
                         limit_price=None, time_in_force="day"):
            return Order(
                order_id="oid-1",
                ticker=ticker.upper(),
                side=side,
                qty=qty,
                order_type=order_type,
                status=OrderStatus.FILLED,
                submitted_at=datetime.utcnow(),
                filled_qty=qty,
                filled_avg_price=123.0,
            )

        def cancel_order(self, order_id: str) -> bool:
            return True

    monkeypatch.setattr(appmod, "BUILD_BROKER", lambda cfg, mode="local": FakeBroker())

    c = _client()
    assert c.post("/connect", json={"broker": "ibkr"}, headers=AUTH).status_code == 200
    assert c.post("/quote", json={"ticker": "aapl"}, headers=AUTH).json()["price"] == 123.0

    ex = c.post("/execute", json={"ticker": "aapl", "qty": 2, "side": "buy"}, headers=AUTH).json()
    assert ex["broker_order_id"] == "oid-1"
    assert ex["status"] == "filled"
    assert ex["quantity"] == 2

    assert c.post("/orders/oid-1/cancel", headers=AUTH).json()["cancelled"] is True
    c.post("/disconnect", headers=AUTH)
