"""Persistence for the broker integration: trade approvals, order mirror,
and the singleton platform broker status.

Mirrors the conventions of :class:`AnalysisRunRepository`: a repository owns a
session and an optional ``user_id`` scope (``None`` = admin / unscoped). Methods
mutate the session; the caller commits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from tradingagents.api.models import BrokerOrder, BrokerStatus, TradeApproval


STATUS_ROW_ID = "platform"

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
SUBMITTED = "submitted"
FAILED = "failed"
EXPIRED = "expired"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_approval_id() -> str:
    return f"appr_{uuid4().hex}"


class BrokerRepository:
    def __init__(self, session: Session, user_id: Optional[str] = None):
        self.session = session
        # None means admin / unscoped (sees everything).
        self.user_id = user_id

    # ------------------------------------------------------------------ #
    # Trade approvals                                                      #
    # ------------------------------------------------------------------ #

    def create_approval(
        self,
        *,
        requested_by_user_id: str,
        ticker: str,
        side: str,
        order_type: str,
        quantity: float,
        run_id: Optional[str] = None,
        conid: Optional[int] = None,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        estimated_price: Optional[float] = None,
        estimated_value: Optional[float] = None,
        whatif_init_margin: Optional[float] = None,
        whatif_commission: Optional[float] = None,
        risk_verdict: Optional[dict[str, Any]] = None,
        agent_reasoning: Optional[str] = None,
    ) -> TradeApproval:
        now = utcnow()
        approval = TradeApproval(
            approval_id=new_approval_id(),
            run_id=run_id,
            requested_by_user_id=requested_by_user_id,
            ticker=ticker.upper(),
            conid=conid,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            time_in_force=time_in_force,
            estimated_price=estimated_price,
            estimated_value=estimated_value,
            whatif_init_margin=whatif_init_margin,
            whatif_commission=whatif_commission,
            risk_verdict=risk_verdict,
            agent_reasoning=agent_reasoning,
            status=PENDING,
            created_at=now,
            updated_at=now,
        )
        self.session.add(approval)
        return approval

    def get_approval(self, approval_id: str) -> Optional[TradeApproval]:
        stmt = select(TradeApproval).where(TradeApproval.approval_id == approval_id)
        if self.user_id is not None:
            stmt = stmt.where(TradeApproval.requested_by_user_id == self.user_id)
        return self.session.scalar(stmt)

    def require_approval(self, approval_id: str) -> TradeApproval:
        approval = self.get_approval(approval_id)
        if approval is None:
            raise LookupError(f"approval {approval_id} not found")
        return approval

    def list_approvals(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[TradeApproval]:
        stmt = select(TradeApproval)
        if self.user_id is not None:
            stmt = stmt.where(TradeApproval.requested_by_user_id == self.user_id)
        if status is not None:
            stmt = stmt.where(TradeApproval.status == status)
        stmt = stmt.order_by(desc(TradeApproval.created_at)).limit(limit)
        return list(self.session.scalars(stmt))

    def _transition(
        self, approval_id: str, allowed_from: set[str], new_status: str
    ) -> TradeApproval:
        approval = self.require_approval(approval_id)
        if approval.status not in allowed_from:
            raise ValueError(
                f"approval {approval_id} is {approval.status!r}; "
                f"cannot move to {new_status!r}"
            )
        approval.status = new_status
        approval.updated_at = utcnow()
        return approval

    def approve(self, approval_id: str, approved_by_user_id: str) -> TradeApproval:
        approval = self._transition(approval_id, {PENDING}, APPROVED)
        approval.approved_by_user_id = approved_by_user_id
        approval.approved_at = utcnow()
        return approval

    def reject(self, approval_id: str, approved_by_user_id: str) -> TradeApproval:
        approval = self._transition(approval_id, {PENDING}, REJECTED)
        approval.approved_by_user_id = approved_by_user_id
        approval.approved_at = utcnow()
        return approval

    def mark_submitted(self, approval_id: str, order_id: str) -> TradeApproval:
        approval = self._transition(approval_id, {APPROVED}, SUBMITTED)
        approval.submitted_order_id = order_id
        return approval

    def mark_failed(self, approval_id: str, error: str) -> TradeApproval:
        approval = self._transition(approval_id, {APPROVED, PENDING}, FAILED)
        approval.error = error
        return approval

    def expire_pending_older_than(self, cutoff: datetime) -> int:
        stmt = select(TradeApproval).where(
            TradeApproval.status == PENDING, TradeApproval.created_at < cutoff
        )
        rows = list(self.session.scalars(stmt))
        for approval in rows:
            approval.status = EXPIRED
            approval.updated_at = utcnow()
        return len(rows)

    # ------------------------------------------------------------------ #
    # Broker orders (mirror)                                               #
    # ------------------------------------------------------------------ #

    def upsert_order(
        self,
        *,
        broker_order_id: str,
        ticker: str,
        side: str,
        order_type: str,
        quantity: float,
        status: str,
        approval_id: Optional[str] = None,
        requested_by_user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        conid: Optional[int] = None,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        filled_qty: float = 0.0,
        filled_avg_price: Optional[float] = None,
        submitted_at: Optional[datetime] = None,
        raw_event: Optional[dict[str, Any]] = None,
    ) -> BrokerOrder:
        order = self.session.get(BrokerOrder, broker_order_id)
        now = utcnow()
        if order is None:
            order = BrokerOrder(
                broker_order_id=broker_order_id,
                approval_id=approval_id,
                requested_by_user_id=requested_by_user_id,
                account_id=account_id,
                ticker=ticker.upper(),
                conid=conid,
                side=side,
                order_type=order_type,
                quantity=quantity,
                limit_price=limit_price,
                time_in_force=time_in_force,
                status=status,
                filled_qty=filled_qty,
                filled_avg_price=filled_avg_price,
                submitted_at=submitted_at or now,
                updated_at=now,
                raw_event=raw_event,
            )
            self.session.add(order)
            return order

        # Update mutable fields on subsequent status/fill events.
        order.status = status
        order.filled_qty = filled_qty
        if filled_avg_price is not None:
            order.filled_avg_price = filled_avg_price
        if approval_id is not None:
            order.approval_id = approval_id
        if requested_by_user_id is not None:
            order.requested_by_user_id = requested_by_user_id
        if raw_event is not None:
            order.raw_event = raw_event
        order.updated_at = now
        return order

    def get_order(self, broker_order_id: str) -> Optional[BrokerOrder]:
        stmt = select(BrokerOrder).where(BrokerOrder.broker_order_id == broker_order_id)
        if self.user_id is not None:
            stmt = stmt.where(BrokerOrder.requested_by_user_id == self.user_id)
        return self.session.scalar(stmt)

    def list_orders(self, limit: int = 100) -> list[BrokerOrder]:
        stmt = select(BrokerOrder)
        if self.user_id is not None:
            stmt = stmt.where(BrokerOrder.requested_by_user_id == self.user_id)
        stmt = stmt.order_by(desc(BrokerOrder.updated_at)).limit(limit)
        return list(self.session.scalars(stmt))

    # ------------------------------------------------------------------ #
    # Platform status singleton                                            #
    # ------------------------------------------------------------------ #

    def get_status(self) -> Optional[BrokerStatus]:
        return self.session.get(BrokerStatus, STATUS_ROW_ID)

    def upsert_status(self, **fields: Any) -> BrokerStatus:
        status = self.session.get(BrokerStatus, STATUS_ROW_ID)
        if status is None:
            status = BrokerStatus(id=STATUS_ROW_ID, **fields)
            status.updated_at = utcnow()
            self.session.add(status)
            return status
        for key, value in fields.items():
            setattr(status, key, value)
        status.updated_at = utcnow()
        return status
