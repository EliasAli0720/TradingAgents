"""Turn an analysis decision into a persisted, sized, risk-checked proposal.

Reuses :class:`SignalMapper` (sizing) and :class:`RiskGate` (advisory first
pass — the enforced pass runs at execution). The proposal is written to
``trade_approvals`` as ``pending``; a human approves it before anything is
placed. This is the non-blocking server replacement for ``AutoTrader``'s
interactive ``input()`` prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from tradingbot.broker.base import OrderSide
from tradingbot.broker.signal_mapper import OrderInstruction, SignalMapper

logger = logging.getLogger(__name__)


@dataclass
class ProposalOutcome:
    created: bool
    approval: Any  # TradeApproval | None (avoid importing the ORM model here)
    reason: str


class TradeProposalBuilder:
    def __init__(self, broker, signal_mapper: SignalMapper, risk_gate=None):
        self._broker = broker
        self._mapper = signal_mapper
        self._risk_gate = risk_gate

    def build(
        self,
        *,
        repo,
        requested_by_user_id: str,
        ticker: str,
        signal: str,
        reasoning: str = "",
        run_id: Optional[str] = None,
    ) -> ProposalOutcome:
        instruction = self._mapper.map(signal)
        if not instruction.should_trade:
            return ProposalOutcome(False, None, instruction.reason)

        try:
            price = self._broker.get_latest_price(ticker)
        except Exception as exc:  # noqa: BLE001
            return ProposalOutcome(False, None, f"price unavailable: {exc}")

        account = self._broker.get_account()
        if instruction.side == OrderSide.BUY:
            qty = self._mapper.compute_buy_qty(instruction, account.cash, price)
            if 0 < qty < 1:
                if account.cash < price:
                    return ProposalOutcome(False, None, "insufficient cash for 1 share")
                qty = 1
        else:
            position = self._broker.get_position(ticker)
            qty = self._mapper.compute_sell_qty(instruction, position.qty if position else 0.0)

        shares = int(qty)
        if shares <= 0:
            return ProposalOutcome(False, None, "computed quantity < 1 share")

        verdict_dict = None
        if self._risk_gate is not None:
            verdict = self._risk_gate.validate(ticker, instruction, shares, price)
            verdict_dict = {
                "approved": verdict.approved,
                "reason": verdict.reason,
                "adjusted_qty": verdict.adjusted_qty,
            }
            if verdict.adjusted_qty is not None:
                shares = int(verdict.adjusted_qty)
            if not verdict.approved and verdict.adjusted_qty is None:
                return ProposalOutcome(False, None, verdict.reason)
            if shares <= 0:
                return ProposalOutcome(False, None, verdict.reason)

        approval = repo.create_approval(
            requested_by_user_id=requested_by_user_id,
            ticker=ticker,
            side=instruction.side.value,
            order_type="market",
            quantity=shares,
            run_id=run_id,
            estimated_price=price,
            estimated_value=shares * price,
            risk_verdict=verdict_dict,
            agent_reasoning=reasoning,
        )
        logger.info(
            "Trade proposal created: %s %s %d (run=%s, user=%s)",
            instruction.side.value.upper(),
            ticker.upper(),
            shares,
            run_id,
            requested_by_user_id,
        )
        return ProposalOutcome(True, approval, "ok")


def _build_risk_gate(config, broker):
    from tradingbot.portfolio.database import PortfolioDatabase
    from tradingbot.risk.gate import RiskGate

    db = PortfolioDatabase(config["db_path"])
    return RiskGate(
        broker=broker,
        db=db,
        max_single_position_pct=config.get("max_single_position_pct", 0.10),
        max_total_exposure_pct=config.get("max_total_exposure_pct", 0.80),
        daily_loss_limit_pct=config.get("daily_loss_limit_pct", -0.02),
        min_cash_reserve=config.get("min_cash_reserve", 1_000.0),
        require_market_open=not config.get("paper_trading", True),
    )


def build_proposal_builder(config, redis_client) -> TradeProposalBuilder:
    """Wire a builder with the server (Redis-proxied) broker + real RiskGate."""
    from tradingbot.broker.factory import build_broker

    cfg = dict(config)
    cfg["redis_client"] = redis_client
    broker = build_broker(cfg, mode="server")
    mapper = SignalMapper(
        full_position_pct=config.get("full_position_pct", 0.05),
        partial_position_pct=config.get("partial_position_pct", 0.03),
        partial_exit_pct=config.get("partial_exit_pct", 0.50),
    )
    return TradeProposalBuilder(broker, mapper, _build_risk_gate(config, broker))
