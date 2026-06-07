"""API tests for the desktop local-execution bridge on /broker:
  POST /broker/local/proposals        — build proposal from a local snapshot
  POST /broker/approvals/{id}/executed — record a locally placed order
  POST /broker/orders/{id}/status      — apply a fill/status update

No Redis / connector / TWS — the snapshot carries the live inputs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api import deps
from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session
from tradingagents.api.models import AnalysisRun, AnalysisRunResult
from tradingagents.api.routers import broker as broker_router

pytestmark = pytest.mark.unit


def _cfg(tmp_path):
    return {
        "db_path": str(tmp_path / "tb.db"),
        "full_position_pct": 0.05,
        "partial_position_pct": 0.03,
        "partial_exit_pct": 0.50,
        "max_single_position_pct": 0.10,
        "max_total_exposure_pct": 0.80,
        "daily_loss_limit_pct": -0.02,
        "min_cash_reserve": 1000.0,
        "paper_trading": True,
    }


def _make_app(tmp_path):
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[deps.get_redis_client] = lambda: None
    app.dependency_overrides[broker_router.get_config] = lambda: _cfg(tmp_path)
    return app, Session


def _register_login(client: TestClient, username: str, password: str) -> None:
    client.post("/auth/register", json={"username": username, "password": password})
    client.post("/auth/login", json={"username": username, "password": password})
    client.headers.update({"X-CSRF-Token": client.cookies.get("tradingagents_csrf")})


def _admin_client(tmp_path):
    app, Session = _make_app(tmp_path)
    client = TestClient(app)
    _register_login(client, "alice", "hunter22a")  # first user -> admin
    return client, Session


def _seed_run(Session, run_id: str, decision: str):
    now = datetime.now(timezone.utc)
    with Session() as s:
        s.add(
            AnalysisRun(
                run_id=run_id,
                status="succeeded",
                ticker="AAPL",
                trade_date=date(2026, 5, 30),
                asset_type="stock",
                analysts=["market"],
                user_id="anyone",
                created_at=now,
                updated_at=now,
            )
        )
        s.add(
            AnalysisRunResult(
                run_id=run_id,
                decision=decision,
                reports={},
                final_state={"final_trade_decision": "buy it"},
                created_at=now,
            )
        )
        s.commit()


_SNAPSHOT = {
    "account": {
        "cash": 100000.0,
        "portfolio_value": 100000.0,
        "buying_power": 400000.0,
        "equity": 100000.0,
    },
    "positions": [],
    "price": 200.0,
}


def test_local_proposal_buy_sizes_and_persists(tmp_path):
    client, Session = _admin_client(tmp_path)
    _seed_run(Session, "run1", "BUY")

    resp = client.post("/broker/local/proposals", json={"run_id": "run1", **_SNAPSHOT})
    assert resp.status_code == 201, resp.text
    appr = resp.json()
    assert appr["side"] == "buy"
    assert appr["status"] == "pending"
    assert appr["quantity"] == 25  # 100000 * 0.05 / 200
    assert appr["risk_verdict"] is not None and appr["risk_verdict"]["approved"] is True
    assert appr["proposal_report"]["summary"] == "BUY AAPL 25 shares at estimated 200.00 (value 5000.00)."
    assert appr["proposal_report"]["sizing"]["final_quantity"] == 25


def test_local_proposal_hold_is_422(tmp_path):
    client, Session = _admin_client(tmp_path)
    _seed_run(Session, "run2", "HOLD")
    resp = client.post("/broker/local/proposals", json={"run_id": "run2", **_SNAPSHOT})
    assert resp.status_code == 422


def test_local_proposal_unknown_run_404(tmp_path):
    client, _ = _admin_client(tmp_path)
    resp = client.post("/broker/local/proposals", json={"run_id": "nope", **_SNAPSHOT})
    assert resp.status_code == 404


def test_executed_then_status_updates_mirror(tmp_path):
    client, Session = _admin_client(tmp_path)
    _seed_run(Session, "run3", "BUY")
    appr = client.post("/broker/local/proposals", json={"run_id": "run3", **_SNAPSHOT}).json()
    aid = appr["approval_id"]

    executed = client.post(
        f"/broker/approvals/{aid}/executed",
        json={"broker_order_id": "ord-1", "status": "submitted", "filled_qty": 0},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "submitted"
    assert executed.json()["order_id"] == "ord-1"

    # approval moved to submitted, mirror row created
    appr_now = client.get("/broker/approvals", params={"status": "submitted"}).json()
    assert any(a["approval_id"] == aid for a in appr_now)
    orders = client.get("/broker/orders").json()
    assert len(orders) == 1 and orders[0]["broker_order_id"] == "ord-1"
    assert orders[0]["approval_id"] == aid

    # a later fill update lands on the same mirror row
    filled = client.post(
        "/broker/orders/ord-1/status",
        json={"status": "filled", "filled_qty": 25, "filled_avg_price": 201.0},
    )
    assert filled.status_code == 200
    assert filled.json()["status"] == "filled"
    assert filled.json()["filled_qty"] == 25
    assert filled.json()["filled_avg_price"] == 201.0


def test_executed_is_idempotent(tmp_path):
    client, Session = _admin_client(tmp_path)
    _seed_run(Session, "run4", "BUY")
    appr = client.post("/broker/local/proposals", json={"run_id": "run4", **_SNAPSHOT}).json()
    aid = appr["approval_id"]
    body = {"broker_order_id": "ord-9", "status": "submitted", "filled_qty": 0}
    assert client.post(f"/broker/approvals/{aid}/executed", json=body).status_code == 200
    # re-report must not error or duplicate
    assert client.post(f"/broker/approvals/{aid}/executed", json=body).status_code == 200
    assert len(client.get("/broker/orders").json()) == 1


def test_manual_order_recorded_and_listed(tmp_path):
    client, _ = _admin_client(tmp_path)
    resp = client.post(
        "/broker/orders/manual",
        json={
            "broker_order_id": "m-1",
            "account_id": "DUMANUAL",
            "ticker": "TSLA",
            "side": "buy",
            "order_type": "market",
            "quantity": 3,
            "status": "filled",
            "filled_qty": 3,
            "filled_avg_price": 250.0,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["broker_order_id"] == "m-1"
    assert resp.json()["approval_id"] is None

    orders = client.get("/broker/orders").json()
    assert any(o["broker_order_id"] == "m-1" and o["ticker"] == "TSLA" for o in orders)
    # and it flows into the per-account trade ledger
    trades = client.get("/broker/trades", params={"account_id": "DUMANUAL"}).json()
    assert any(r["ticker"] == "TSLA" for r in trades["trades"])


def test_manual_order_rejects_negative_quantity(tmp_path):
    client, _ = _admin_client(tmp_path)

    response = client.post(
        "/broker/orders/manual",
        json={
            "broker_order_id": "ord-bad",
            "account_id": "DU1",
            "ticker": "AAPL",
            "side": "buy",
            "order_type": "market",
            "quantity": -1,
        },
    )

    assert response.status_code == 422


def test_orders_can_be_filtered_by_account_id(tmp_path):
    client, _ = _admin_client(tmp_path)
    for account_id, ticker in (("DUWEBULL", "AAPL"), ("DULOCAL", "MSFT")):
        resp = client.post(
            "/broker/orders/manual",
            json={
                "broker_order_id": f"m-{account_id}",
                "account_id": account_id,
                "ticker": ticker,
                "side": "buy",
                "order_type": "market",
                "quantity": 1,
                "status": "filled",
                "filled_qty": 1,
                "filled_avg_price": 100.0,
            },
        )
        assert resp.status_code == 200, resp.text

    webull_orders = client.get("/broker/orders", params={"account_id": "DUWEBULL"}).json()
    assert [order["ticker"] for order in webull_orders] == ["AAPL"]


def test_manual_order_requires_trader_role(tmp_path):
    client, _ = _admin_client(tmp_path)
    viewer = TestClient(client.app)
    _register_login(viewer, "bob", "hunter22b")
    resp = viewer.post(
        "/broker/orders/manual",
        json={
            "broker_order_id": "m-2",
            "account_id": "DUMANUAL",
            "ticker": "TSLA",
            "side": "buy",
            "quantity": 1,
        },
    )
    assert resp.status_code == 403


def test_executed_requires_trader_role(tmp_path):
    client, Session = _admin_client(tmp_path)
    _seed_run(Session, "run5", "BUY")
    appr = client.post("/broker/local/proposals", json={"run_id": "run5", **_SNAPSHOT}).json()

    viewer = TestClient(client.app)
    _register_login(viewer, "bob", "hunter22b")  # second user -> viewer
    resp = viewer.post(
        f"/broker/approvals/{appr['approval_id']}/executed",
        json={"broker_order_id": "x", "status": "submitted"},
    )
    assert resp.status_code == 403
