"""Server-side portfolio analytics scoped to (user, account):
  GET  /broker/performance  — metrics + equity curve
  GET  /broker/trades       — trade ledger + closed round-trips (realised P&L)
  POST /broker/snapshot     — push equity snapshot

Trade history + realised P&L derive from broker_orders; no local SQLite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api import deps
from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session
from tradingagents.api.models import BrokerOrder

pytestmark = pytest.mark.unit

ACC = "DUTEST01"
OTHER = "DUOTHER9"


def _make_app():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[deps.get_redis_client] = lambda: None
    return app, Session


def _login(client: TestClient, username: str, password: str) -> str:
    client.post("/auth/register", json={"username": username, "password": password})
    client.post("/auth/login", json={"username": username, "password": password})
    client.headers.update({"X-CSRF-Token": client.cookies.get("tradingagents_csrf")})
    return client.get("/auth/me").json()["user_id"]


_t0 = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)


def _seed_order(Session, user_id, account_id, side, qty, price, ticker="AAPL", seq=0):
    with Session() as s:
        when = _t0 + timedelta(minutes=seq)
        s.add(
            BrokerOrder(
                broker_order_id=f"ord-{uuid4().hex[:8]}",
                requested_by_user_id=user_id,
                account_id=account_id,
                ticker=ticker,
                side=side,
                order_type="market",
                quantity=qty,
                status="filled",
                filled_qty=qty,
                filled_avg_price=price,
                submitted_at=when,
                updated_at=when,
            )
        )
        s.commit()


def test_trades_and_realized_pnl_from_orders():
    app, Session = _make_app()
    client = TestClient(app)
    uid = _login(client, "alice", "hunter22a")
    _seed_order(Session, uid, ACC, "buy", 10, 100.0, seq=0)
    _seed_order(Session, uid, ACC, "sell", 10, 120.0, seq=1)

    trades = client.get("/broker/trades", params={"account_id": ACC}).json()
    assert len(trades["trades"]) == 2
    assert len(trades["closed"]) == 1
    closed = trades["closed"][0]
    assert closed["realized_pnl"] == 200.0  # (120 - 100) * 10
    assert closed["entry_price"] == 100.0 and closed["exit_price"] == 120.0


def test_performance_metrics():
    app, Session = _make_app()
    client = TestClient(app)
    uid = _login(client, "alice", "hunter22a")
    _seed_order(Session, uid, ACC, "buy", 10, 100.0, seq=0)
    _seed_order(Session, uid, ACC, "sell", 10, 120.0, seq=1)  # +200 win
    _seed_order(Session, uid, ACC, "buy", 5, 50.0, ticker="MSFT", seq=2)
    _seed_order(Session, uid, ACC, "sell", 5, 40.0, ticker="MSFT", seq=3)  # -50 loss

    perf = client.get("/broker/performance", params={"account_id": ACC}).json()
    assert perf["total_trades"] == 2
    assert perf["winning_trades"] == 1
    assert perf["losing_trades"] == 1
    assert perf["win_rate"] == 0.5
    assert perf["total_realized_pnl"] == 150.0
    assert perf["profit_factor"] == 4.0  # 200 / 50


def test_snapshot_feeds_equity_curve():
    app, Session = _make_app()
    client = TestClient(app)
    _login(client, "alice", "hunter22a")
    r = client.post(
        "/broker/snapshot",
        json={"account_id": ACC, "cash": 9000, "invested_value": 1200, "total_value": 10200, "open_positions": 1},
    )
    assert r.status_code == 200
    perf = client.get("/broker/performance", params={"account_id": ACC}).json()
    assert len(perf["equity_curve"]) == 1
    assert perf["current_equity"] == 10200
    # idempotent same-day upsert: still one row
    client.post("/broker/snapshot", json={"account_id": ACC, "total_value": 10500, "cash": 9000, "invested_value": 1500, "open_positions": 1})
    perf2 = client.get("/broker/performance", params={"account_id": ACC}).json()
    assert len(perf2["equity_curve"]) == 1
    assert perf2["current_equity"] == 10500


def test_account_segmentation():
    app, Session = _make_app()
    client = TestClient(app)
    uid = _login(client, "alice", "hunter22a")
    _seed_order(Session, uid, ACC, "buy", 10, 100.0, seq=0)
    _seed_order(Session, uid, ACC, "sell", 10, 120.0, seq=1)

    # a different account for the same user sees nothing
    other = client.get("/broker/trades", params={"account_id": OTHER}).json()
    assert other["trades"] == [] and other["closed"] == []
    perf = client.get("/broker/performance", params={"account_id": OTHER}).json()
    assert perf["total_trades"] == 0


def test_user_segmentation():
    app, Session = _make_app()
    client = TestClient(app)
    uid_a = _login(client, "alice", "hunter22a")
    _seed_order(Session, uid_a, ACC, "buy", 10, 100.0, seq=0)
    _seed_order(Session, uid_a, ACC, "sell", 10, 120.0, seq=1)

    bob = TestClient(app)
    _login(bob, "bob", "hunter22b")  # different user, same account id
    trades = bob.get("/broker/trades", params={"account_id": ACC}).json()
    assert trades["trades"] == []  # bob can't see alice's account activity


def test_performance_requires_auth():
    app, _ = _make_app()
    assert TestClient(app).get("/broker/performance", params={"account_id": ACC}).status_code == 401
