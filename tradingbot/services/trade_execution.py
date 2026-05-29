"""Execute an approved trade: re-check, preview, place, mirror.

Runs only on a ``trade_approvals`` row in state ``approved``. Re-reads the live
price, runs the *enforced* RiskGate pass, previews margin via ``whatIf``, places
the order, and mirrors it into ``broker_orders``. IBKR fills are asynchronous,
so we record the order at ``submitted`` and let the connector's event mirror
update the fill — we do NOT record a fill here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from tradingbot.broker.base import OrderSide, OrderType
from tradingbot.broker.signal_mapper import OrderInstruction

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    order_id: Optional[str]
    status: str  # "submitted" | "failed"
    detail: str


class TradeExecutionService:
    def __init__(self, broker, risk_gate=None, portfolio_manager=None):
        self._broker = broker
        self._risk_gate = risk_gate
        self._portfolio_manager = portfolio_manager

    def execute_approved(
        self,
        *,
        repo,
        approval_id: str,
        actor_user_id: str,
        account_id: Optional[str] = None,
    ) -> ExecutionResult:
        approval = repo.require_approval(approval_id)
        if approval.status != "approved":
            raise ValueError(
                f"approval {approval_id} is {approval.status!r}, not 'approved'"
            )

        side = OrderSide(approval.side)
        order_type = OrderType(approval.order_type)
        qty = int(approval.quantity)
        ticker = approval.ticker

        # Re-read price (markets move between approval and execution).
        try:
            price = self._broker.get_latest_price(ticker)
        except Exception as exc:  # noqa: BLE001
            repo.mark_failed(approval_id, f"price unavailable: {exc}")
            return ExecutionResult(None, "failed", str(exc))

        # Enforced second risk pass.
        if self._risk_gate is not None:
            instruction = OrderInstruction(
                should_trade=True,
                side=side,
                allocation_fraction=0.0,
                reason="execution recheck",
            )
            verdict = self._risk_gate.validate(ticker, instruction, qty, price)
            if not verdict.approved:
                repo.mark_failed(approval_id, f"risk gate: {verdict.reason}")
                return ExecutionResult(None, "failed", verdict.reason)
            if verdict.adjusted_qty:
                qty = int(verdict.adjusted_qty)
                if qty <= 0:
                    repo.mark_failed(approval_id, "risk gate adjusted qty to 0")
                    return ExecutionResult(None, "failed", "qty adjusted to 0")

        # whatIf preview (best-effort; stored for the audit trail).
        try:
            preview = self._broker.preview_order(
                ticker, qty, side, order_type, approval.limit_price, approval.time_in_force
            )
            approval.whatif_init_margin = preview.get("init_margin")
            approval.whatif_commission = preview.get("commission")
        except Exception as exc:  # noqa: BLE001
            logger.warning("whatIf preview failed for %s: %s", ticker, exc)

        # Place — never retried (avoid duplicate orders).
        try:
            order = self._broker.submit_order(
                ticker, qty, side, order_type, approval.limit_price, approval.time_in_force
            )
        except Exception as exc:  # noqa: BLE001
            repo.mark_failed(approval_id, f"order failed: {exc}")
            return ExecutionResult(None, "failed", str(exc))

        repo.upsert_order(
            broker_order_id=order.order_id,
            ticker=order.ticker,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.qty,
            status=order.status.value,
            approval_id=approval_id,
            requested_by_user_id=approval.requested_by_user_id,
            account_id=account_id,
            limit_price=order.limit_price,
            filled_qty=order.filled_qty,
            filled_avg_price=order.filled_avg_price,
        )
        repo.mark_submitted(approval_id, order.order_id)

        # Legacy PortfolioManager (SQLite + reflection) only records real fills;
        # IBKR fills arrive asynchronously, so only act if already filled.
        if self._portfolio_manager is not None and order.status.value == "filled":
            try:
                self._portfolio_manager.record_trade(
                    order, signal=approval.side, agent_reasoning=approval.agent_reasoning or ""
                )
            except Exception:  # noqa: BLE001
                logger.exception("PortfolioManager.record_trade failed for %s", ticker)

        logger.info(
            "Executed approval %s -> order %s (%s)", approval_id, order.order_id, order.status.value
        )
        return ExecutionResult(order.order_id, "submitted", "submitted")


def build_execution_service(config, redis_client) -> TradeExecutionService:
    from tradingbot.broker.factory import build_broker
    from tradingbot.services.trade_proposal import _build_risk_gate

    cfg = dict(config)
    cfg["redis_client"] = redis_client
    broker = build_broker(cfg, mode="server")
    return TradeExecutionService(broker, _build_risk_gate(config, broker))
