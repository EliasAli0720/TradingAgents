"""Unit tests for TradeProposalBuilder and TradeExecutionService.

Wires a real BrokerRepository (in-memory sqlite) + a real IBKRBroker backed by
the shared FakeIBKRConnection + a fake RiskGate, so the proposal/approval/
execution flow is exercised without a live gateway or PortfolioDatabase.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.broker_repository import BrokerRepository
from tradingagents.api.db import Base
from tradingbot.broker.ibkr import IBKRBroker
from tradingbot.broker.ibkr_connection import AccountValue, Quote, RawPosition, WhatIfResult
from tradingbot.broker.signal_mapper import SignalMapper
from tradingbot.risk.gate import RiskVerdict
from tradingbot.services.trade_execution import TradeExecutionService
from tradingbot.services.trade_proposal import TradeProposalBuilder
from tests.ibkr_fakes import FakeIBKRConnection

pytestmark = pytest.mark.unit


def _repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    return BrokerRepository(session), session


def _broker(cash=100_000.0, price=200.0, positions=None):
    conn = FakeIBKRConnection(
        summary=[AccountValue("AvailableFunds", str(cash), "USD")],
        quote=Quote(last=price),
        positions=positions or [],
        whatif=WhatIfResult(init_margin=1000.0, commission=1.0),
    )
    return IBKRBroker(conn, account_id="DU1"), conn


class _FakeRiskGate:
    def __init__(self, verdict: RiskVerdict):
        self._verdict = verdict
        self.calls = 0

    def validate(self, ticker, instruction, qty, price):
        self.calls += 1
        return self._verdict


# --------------------------------------------------------------------------- #
# Proposal builder                                                            #
# --------------------------------------------------------------------------- #


def test_buy_proposal_sized_and_persisted():
    repo, session = _repo()
    broker, _ = _broker(cash=100_000.0, price=200.0)
    builder = TradeProposalBuilder(broker, SignalMapper())  # full_pct 0.05
    out = builder.build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="BUY", run_id="run1"
    )
    session.commit()
    assert out.created
    assert out.approval.side == "buy"
    assert out.approval.quantity == 25  # 100000 * 0.05 / 200
    assert out.approval.estimated_value == pytest.approx(5000.0)
    assert out.approval.status == "pending"


def test_buy_proposal_includes_explanation_report():
    repo, session = _repo()
    broker, _ = _broker(cash=100_000.0, price=200.0)
    builder = TradeProposalBuilder(broker, SignalMapper())
    out = builder.build(
        repo=repo,
        requested_by_user_id="u1",
        ticker="AAPL",
        signal="BUY",
        reasoning="Portfolio manager recommends accumulation after debate.",
        run_id="run-report",
    )
    session.commit()

    assert out.created
    report = out.approval.proposal_report
    assert report["summary"] == "BUY AAPL 25 shares at estimated 200.00 (value 5000.00)."
    assert report["signal"]["raw"] == "BUY"
    assert report["signal"]["normalized"] == "BUY"
    assert report["signal"]["action"] == "buy"
    assert report["sizing"]["basis"] == "cash"
    assert report["sizing"]["basis_amount"] == 100_000.0
    assert report["sizing"]["allocation_fraction"] == 0.05
    assert report["sizing"]["target_value"] == 5_000.0
    assert report["sizing"]["estimated_price"] == 200.0
    assert report["sizing"]["computed_quantity"] == 25.0
    assert report["sizing"]["final_quantity"] == 25
    assert report["sizing"]["estimated_value"] == 5_000.0
    assert report["risk"]["approved"] is None
    assert report["risk"]["reason"] == "No advisory risk gate configured"
    assert report["agent_reasoning"] == "Portfolio manager recommends accumulation after debate."


def test_buy_proposal_accepts_rating_markdown_decision():
    repo, session = _repo()
    broker, _ = _broker(cash=100_000.0, price=200.0)
    builder = TradeProposalBuilder(broker, SignalMapper())
    out = builder.build(
        repo=repo,
        requested_by_user_id="u1",
        ticker="AAPL",
        signal="**Rating**: Buy\n\nEnter gradually near support.",
        run_id="run-rating-buy",
    )
    session.commit()
    assert out.created
    assert out.approval.side == "buy"
    assert out.approval.quantity == 25


def test_buy_proposal_uses_one_share_minimum_when_affordable():
    repo, session = _repo()
    broker, _ = _broker(cash=5_000.0, price=420.0)
    builder = TradeProposalBuilder(broker, SignalMapper())  # target = 250 / 420 < 1 share
    out = builder.build(
        repo=repo, requested_by_user_id="u1", ticker="MSFT", signal="BUY", run_id="run-msft"
    )
    session.commit()
    assert out.created
    assert out.approval.quantity == 1
    assert out.approval.estimated_value == pytest.approx(420.0)


def test_buy_proposal_rejected_when_one_share_is_not_affordable():
    repo, _ = _repo()
    broker, _ = _broker(cash=300.0, price=420.0)
    out = TradeProposalBuilder(broker, SignalMapper()).build(
        repo=repo, requested_by_user_id="u1", ticker="MSFT", signal="BUY"
    )
    assert out.created is False
    assert out.reason == "insufficient cash for 1 share"


def test_hold_signal_creates_nothing():
    repo, _ = _repo()
    broker, _ = _broker()
    out = TradeProposalBuilder(broker, SignalMapper()).build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="HOLD"
    )
    assert out.created is False
    assert repo.list_approvals() == []


def test_sell_proposal_uses_held_quantity():
    repo, session = _repo()
    broker, _ = _broker(positions=[RawPosition("AAPL", 1, 10, 150.0)])
    out = TradeProposalBuilder(broker, SignalMapper()).build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="SELL"
    )
    session.commit()
    assert out.created
    assert out.approval.side == "sell"
    assert out.approval.quantity == 10  # full exit


def test_sell_without_position_is_skipped():
    repo, _ = _repo()
    broker, _ = _broker(positions=[])
    out = TradeProposalBuilder(broker, SignalMapper()).build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="SELL"
    )
    assert out.created is False


def test_risk_gate_caps_quantity():
    repo, session = _repo()
    broker, _ = _broker(cash=100_000.0, price=200.0)
    gate = _FakeRiskGate(RiskVerdict(approved=True, reason="capped", adjusted_qty=5))
    out = TradeProposalBuilder(broker, SignalMapper(), risk_gate=gate).build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="BUY"
    )
    session.commit()
    assert out.created
    assert out.approval.quantity == 5
    assert out.approval.risk_verdict["reason"] == "capped"
    assert out.approval.proposal_report["risk"]["adjusted_qty"] == 5
    assert out.approval.proposal_report["sizing"]["final_quantity"] == 5


def test_risk_gate_zero_qty_blocks_proposal():
    repo, _ = _repo()
    broker, _ = _broker()
    gate = _FakeRiskGate(RiskVerdict(approved=False, reason="too big", adjusted_qty=0))
    out = TradeProposalBuilder(broker, SignalMapper(), risk_gate=gate).build(
        repo=repo, requested_by_user_id="u1", ticker="AAPL", signal="BUY"
    )
    assert out.created is False


# --------------------------------------------------------------------------- #
# Execution service                                                           #
# --------------------------------------------------------------------------- #


def _approved(repo, session):
    approval = repo.create_approval(
        requested_by_user_id="u1",
        ticker="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        estimated_price=200.0,
    )
    repo.approve(approval.approval_id, "admin1")
    session.commit()
    return approval


def test_execute_places_and_mirrors_order():
    repo, session = _repo()
    approval = _approved(repo, session)
    broker, conn = _broker()
    svc = TradeExecutionService(broker, risk_gate=None)

    result = svc.execute_approved(repo=repo, approval_id=approval.approval_id, actor_user_id="admin1")
    session.commit()

    assert result.status == "submitted"
    assert conn.place_calls == 1
    assert approval.status == "submitted"
    assert approval.submitted_order_id == result.order_id
    mirror = repo.get_order(result.order_id)
    assert mirror is not None
    assert mirror.ticker == "AAPL"
    assert mirror.approval_id == approval.approval_id
    assert mirror.account_id == "DU1"
    assert mirror.broker == "ibkr"


def test_execute_requires_approved_state():
    repo, session = _repo()
    approval = repo.create_approval(
        requested_by_user_id="u1", ticker="AAPL", side="buy", order_type="market", quantity=1
    )
    session.commit()
    broker, _ = _broker()
    with pytest.raises(ValueError):
        TradeExecutionService(broker).execute_approved(
            repo=repo, approval_id=approval.approval_id, actor_user_id="admin1"
        )


def test_execute_blocked_by_risk_gate_marks_failed():
    repo, session = _repo()
    approval = _approved(repo, session)
    broker, conn = _broker()
    gate = _FakeRiskGate(RiskVerdict(approved=False, reason="exposure cap"))
    svc = TradeExecutionService(broker, risk_gate=gate)

    result = svc.execute_approved(repo=repo, approval_id=approval.approval_id, actor_user_id="admin1")
    session.commit()
    assert result.status == "failed"
    assert approval.status == "failed"
    assert conn.place_calls == 0  # never placed


def test_execute_broker_error_marks_failed():
    repo, session = _repo()
    approval = _approved(repo, session)
    conn = FakeIBKRConnection(
        summary=[AccountValue("AvailableFunds", "100000", "USD")],
        quote=Quote(last=200.0),
        place_raises=RuntimeError("rejected by IBKR"),
    )
    broker = IBKRBroker(conn)
    svc = TradeExecutionService(broker, risk_gate=None)

    result = svc.execute_approved(repo=repo, approval_id=approval.approval_id, actor_user_id="admin1")
    session.commit()
    assert result.status == "failed"
    assert approval.status == "failed"
    assert conn.place_calls == 1  # attempted once, not retried
