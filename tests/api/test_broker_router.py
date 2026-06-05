"""API tests for the /broker router: auth, roles, status, approval workflow.

The live broker + proposal/execution services are overridden with fakes, so no
Redis, connector, or TWS is needed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api import deps
from tradingagents.api.broker_credential_repository import BrokerCredentialRepository
from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session
from tradingagents.api.models import AnalysisRun, AnalysisRunResult
from tradingagents.api.routers import broker as broker_router
from tradingbot.broker.ibkr import IBKRBroker
from tradingbot.broker.ibkr_connection import AccountValue, Quote, WhatIfResult
from tradingbot.broker.signal_mapper import SignalMapper
from tradingbot.services import TradeExecutionService, TradeProposalBuilder
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


def _fake_broker():
    conn = FakeIBKRConnection(
        summary=[
            AccountValue("AvailableFunds", "100000", "USD"),
            AccountValue("NetLiquidation", "100000", "USD"),
            AccountValue("BuyingPower", "400000", "USD"),
            AccountValue("TotalCashValue", "100000", "USD"),
        ],
        quote=Quote(last=200.0),
        whatif=WhatIfResult(init_margin=5000.0, commission=1.0),
    )
    return IBKRBroker(conn, account_id="DU1")


def _make_app():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    broker = _fake_broker()
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[deps.get_redis_client] = lambda: None
    app.dependency_overrides[broker_router.get_broker] = lambda: broker
    app.dependency_overrides[broker_router.get_proposal_builder] = lambda: TradeProposalBuilder(
        broker, SignalMapper(), None
    )
    app.dependency_overrides[broker_router.get_execution_service] = lambda: TradeExecutionService(
        broker, None
    )
    return app, Session


def _register_login(client: TestClient, username: str, password: str) -> None:
    client.post("/auth/register", json={"username": username, "password": password})
    client.post("/auth/login", json={"username": username, "password": password})
    client.headers.update({"X-CSRF-Token": client.cookies.get("tradingagents_csrf")})


def _admin_client(*, raise_server_exceptions: bool = True):
    app, Session = _make_app()
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    _register_login(client, "alice", "hunter22a")  # first user -> admin
    return client, Session, app


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


# --------------------------------------------------------------------------- #
# Auth / roles                                                                #
# --------------------------------------------------------------------------- #


def test_status_requires_auth():
    app, _ = _make_app()
    client = TestClient(app)
    assert client.get("/broker/status").status_code == 401


def test_viewer_cannot_preview():
    client, _, app = _admin_client()
    bob = TestClient(app)
    _register_login(bob, "bob", "hunter22b")  # second user -> viewer
    resp = bob.post(
        "/broker/orders/preview",
        json={"ticker": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Status / account / positions                                                #
# --------------------------------------------------------------------------- #


def test_status_not_connected_when_no_mirror_row():
    client, _, _ = _admin_client()
    body = client.get("/broker/status").json()
    assert body["connected"] is False
    assert body["gateway_online"] is False
    assert body["accounts"] == []
    assert body["last_error"] == "connector not running"


def test_refresh_status_reports_active_webull_credential():
    client, Session, _ = _admin_client()
    with Session() as s:
        user_id = s.query(broker_router.User).filter_by(username="alice").one().user_id
        BrokerCredentialRepository(s, user_id).upsert_api_key(
            app_key="key",
            app_secret="secret",
            account_id="DUWEBULL",
        )
        s.commit()

    body = client.post("/broker/refresh").json()
    assert body["broker"] == "webull"
    assert body["connected"] is True
    assert body["account_id"] == "DUWEBULL"
    assert body["accounts"] == ["DUWEBULL"]


def test_account_and_positions_from_broker():
    client, _, _ = _admin_client()
    acct = client.get("/broker/account").json()
    assert acct["cash"] == 100000.0
    assert acct["portfolio_value"] == 100000.0
    assert client.get("/broker/positions").json() == []


def test_preview_order_ok_for_admin():
    client, _, _ = _admin_client()
    resp = client.post(
        "/broker/orders/preview",
        json={"ticker": "AAPL", "qty": 10, "side": "buy", "order_type": "market"},
    )
    assert resp.status_code == 200
    assert resp.json()["init_margin"] == 5000.0


def test_preview_order_validation_error_returns_422():
    client, _, app = _admin_client(raise_server_exceptions=False)

    class BadPreviewBroker:
        def preview_order(self, *args, **kwargs):
            raise ValueError("limit_price is required for LIMIT orders")

    app.dependency_overrides[broker_router.get_broker] = lambda: BadPreviewBroker()

    resp = client.post(
        "/broker/orders/preview",
        json={"ticker": "AAPL", "qty": 10, "side": "buy", "order_type": "limit"},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "limit_price is required for LIMIT orders"


def test_preview_order_broker_failure_returns_502():
    client, _, app = _admin_client(raise_server_exceptions=False)

    class FailingPreviewBroker:
        def preview_order(self, *args, **kwargs):
            raise RuntimeError("Parameter error, invalid combo_type")

    app.dependency_overrides[broker_router.get_broker] = lambda: FailingPreviewBroker()

    resp = client.post(
        "/broker/orders/preview",
        json={"ticker": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Parameter error, invalid combo_type"


def test_place_manual_server_order_mirrors_order():
    client, _, _ = _admin_client()
    resp = client.post(
        "/broker/orders",
        json={"ticker": "MSFT", "qty": 2, "side": "buy", "order_type": "market"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["broker_order_id"] == "O1"
    assert body["ticker"] == "MSFT"
    assert body["side"] == "buy"
    assert body["quantity"] == 2
    assert body["status"] == "pending"
    assert body["approval_id"] is None
    assert body["account_id"] == "DU1"

    orders = client.get("/broker/orders").json()
    assert any(o["broker_order_id"] == "O1" and o["ticker"] == "MSFT" for o in orders)


def test_viewer_cannot_place_manual_server_order():
    client, _, app = _admin_client()
    bob = TestClient(app)
    _register_login(bob, "bob", "hunter22b")
    resp = bob.post(
        "/broker/orders",
        json={"ticker": "MSFT", "qty": 1, "side": "buy", "order_type": "market"},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Approval workflow                                                           #
# --------------------------------------------------------------------------- #


def test_create_proposal_then_approve_places_order():
    client, Session, _ = _admin_client()
    _seed_run(Session, "run1", "BUY")

    created = client.post("/broker/approvals", json={"run_id": "run1"})
    assert created.status_code == 201
    approval = created.json()
    assert approval["status"] == "pending"
    assert approval["side"] == "buy"
    assert approval["quantity"] == 25  # 100000 * 0.05 / 200
    assert approval["proposal_report"]["summary"] == (
        "BUY AAPL 25 shares at estimated 200.00 (value 5000.00)."
    )
    assert approval["proposal_report"]["sizing"]["final_quantity"] == 25
    assert approval["proposal_report"]["agent_reasoning"] == "buy it"

    approved = client.post(f"/broker/approvals/{approval['approval_id']}/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "submitted"
    assert body["order_id"]

    orders = client.get("/broker/orders").json()
    assert len(orders) == 1
    assert orders[0]["ticker"] == "AAPL"
    assert orders[0]["approval_id"] == approval["approval_id"]


def test_proposal_rejected_when_signal_is_hold():
    client, Session, _ = _admin_client()
    _seed_run(Session, "run2", "HOLD")
    resp = client.post("/broker/approvals", json={"run_id": "run2"})
    assert resp.status_code == 422


def test_create_proposal_unknown_run_404():
    client, _, _ = _admin_client()
    resp = client.post("/broker/approvals", json={"run_id": "nope"})
    assert resp.status_code == 404


def test_approve_unknown_approval_404():
    client, _, _ = _admin_client()
    resp = client.post("/broker/approvals/missing/approve")
    assert resp.status_code == 404


def test_reject_then_approve_conflicts():
    client, Session, _ = _admin_client()
    _seed_run(Session, "run3", "BUY")
    approval = client.post("/broker/approvals", json={"run_id": "run3"}).json()
    aid = approval["approval_id"]

    rejected = client.post(f"/broker/approvals/{aid}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # Approving a rejected proposal is an illegal transition.
    conflict = client.post(f"/broker/approvals/{aid}/approve")
    assert conflict.status_code == 409


def test_cancel_order_endpoint():
    client, Session, _ = _admin_client()
    _seed_run(Session, "run4", "BUY")
    approval = client.post("/broker/approvals", json={"run_id": "run4"}).json()
    approved = client.post(f"/broker/approvals/{approval['approval_id']}/approve").json()
    order_id = approved["order_id"]

    resp = client.post(f"/broker/orders/{order_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True

    orders = client.get("/broker/orders").json()
    saved = next(o for o in orders if o["broker_order_id"] == order_id)
    assert saved["status"] == "cancelled"
