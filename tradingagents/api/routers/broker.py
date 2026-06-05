"""Broker (IBKR) API — status, account, positions, orders, and the trade
approval workflow. Web processes never touch the socket: reads of state come
from the DB mirror, and live calls proxy to the single connector over Redis.

Reads require any authenticated user (the platform account is shared). Placing,
approving, rejecting, cancelling and previewing require admin/operator.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from tradingagents.api.broker_repository import BrokerRepository
from tradingagents.api.deps import (
    get_current_user,
    get_db_session,
    get_redis_client,
    require_role,
)
from tradingagents.api.models import AnalysisRunResult, User
from tradingagents.api.repositories import AnalysisRunRepository
from tradingbot.broker.base import OrderSide, OrderType
from tradingbot.services import (
    BrokerConnectionService,
    TradeExecutionService,
    TradeProposalBuilder,
)

router = APIRouter(prefix="/broker", tags=["broker"])

_TRADER_ROLES = ("admin", "operator")


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class BrokerStatusResponse(BaseModel):
    broker: str
    connected: bool
    gateway_online: bool
    brokerage_session: bool
    account_id: Optional[str]
    accounts: list[str] = Field(default_factory=list)
    paper: bool
    last_refresh_at: Optional[str]
    last_error: Optional[str]


class AccountResponse(BaseModel):
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float


class PositionResponse(BaseModel):
    ticker: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    side: str


class OrderResponse(BaseModel):
    broker_order_id: str
    account_id: Optional[str] = None
    broker: str = "ibkr"
    ticker: str
    side: str
    order_type: str
    quantity: float
    status: str
    filled_qty: float
    filled_avg_price: Optional[float]
    limit_price: Optional[float]
    approval_id: Optional[str]
    submitted_at: Optional[str]
    updated_at: Optional[str]


class ApprovalResponse(BaseModel):
    approval_id: str
    run_id: Optional[str]
    ticker: str
    side: str
    order_type: str
    quantity: float
    limit_price: Optional[float]
    time_in_force: str
    estimated_price: Optional[float]
    estimated_value: Optional[float]
    whatif_init_margin: Optional[float]
    whatif_commission: Optional[float]
    risk_verdict: Optional[dict[str, Any]]
    agent_reasoning: Optional[str]
    proposal_report: Optional[dict[str, Any]]
    status: str
    requested_by_user_id: str
    approved_by_user_id: Optional[str]
    submitted_order_id: Optional[str]
    error: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class PreviewRequest(BaseModel):
    ticker: str
    qty: int
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[float] = None
    time_in_force: str = "day"


class PreviewResponse(BaseModel):
    init_margin: Optional[float] = None
    maint_margin: Optional[float] = None
    commission: Optional[float] = None
    equity_with_loan: Optional[float] = None
    warning: Optional[str] = None


class PlaceOrderRequest(BaseModel):
    ticker: str
    qty: int
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[float] = None
    time_in_force: str = "day"


class CreateProposalRequest(BaseModel):
    run_id: str


class ApproveResponse(BaseModel):
    approval_id: str
    status: str
    order_id: Optional[str]
    detail: str


class CancelResponse(BaseModel):
    cancelled: bool


# Local-execution bridge (desktop): the server builds the proposal + risk
# verdict from a snapshot of the user's local account, and records the order
# the local sidecar placed. Additive — the server-connector path is untouched.


class AccountSnap(BaseModel):
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float


class PositionSnap(BaseModel):
    ticker: str
    qty: float
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    side: str = "long"


class LocalProposalRequest(BaseModel):
    run_id: str
    account: AccountSnap
    positions: list[PositionSnap] = []
    price: float


class ExecutedRequest(BaseModel):
    broker_order_id: str
    status: str = "submitted"
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None
    account_id: Optional[str] = None
    broker: str = "ibkr"


class OrderStatusRequest(BaseModel):
    status: str
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None


class SnapshotRequest(BaseModel):
    account_id: str
    broker: str = "ibkr"
    cash: float = 0.0
    invested_value: float = 0.0
    total_value: float = 0.0
    open_positions: int = 0


class ManualOrderRequest(BaseModel):
    broker_order_id: str
    account_id: str
    broker: str = "ibkr"
    ticker: str
    side: str
    order_type: str = "market"
    quantity: float
    status: str = "submitted"
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None


# --------------------------------------------------------------------------- #
# Dependencies (overridable in tests)                                         #
# --------------------------------------------------------------------------- #


def get_config() -> dict:
    from tradingbot.config import TRADINGBOT_CONFIG

    return TRADINGBOT_CONFIG


def get_connection_service(
    config: dict = Depends(get_config),
    redis_client=Depends(get_redis_client),
) -> BrokerConnectionService:
    return BrokerConnectionService(config, redis_client)


def get_broker(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    svc: BrokerConnectionService = Depends(get_connection_service),
    config: dict = Depends(get_config),
    redis_client=Depends(get_redis_client),
):
    """Resolve the broker for the current user.

    Webull-connected users get a per-user cloud broker (no Redis); everyone else
    falls through to the IBKR connector path, which requires Redis.
    """
    from tradingagents.api.broker_provider import resolve_active_broker

    if resolve_active_broker(session, user, config) == "webull":
        from tradingagents.api.broker_provider import build_user_broker

        try:
            return build_user_broker(session, user, config, svc)
        except (LookupError, PermissionError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc

    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="broker channel unavailable",
        )
    return svc.build_broker()


def get_proposal_builder(
    broker=Depends(get_broker), config: dict = Depends(get_config)
) -> TradeProposalBuilder:
    from tradingbot.broker.signal_mapper import SignalMapper
    from tradingbot.services.trade_proposal import _build_risk_gate

    mapper = SignalMapper(
        full_position_pct=config.get("full_position_pct", 0.05),
        partial_position_pct=config.get("partial_position_pct", 0.03),
        partial_exit_pct=config.get("partial_exit_pct", 0.50),
    )
    return TradeProposalBuilder(broker, mapper, _build_risk_gate(config, broker))


def get_execution_service(
    broker=Depends(get_broker), config: dict = Depends(get_config)
) -> TradeExecutionService:
    from tradingbot.services.trade_proposal import _build_risk_gate

    return TradeExecutionService(broker, _build_risk_gate(config, broker))


def get_broker_repo(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> BrokerRepository:
    user_id = None if user.role == "admin" else user.user_id
    return BrokerRepository(session, user_id=user_id)


# --------------------------------------------------------------------------- #
# Serialization helpers                                                       #
# --------------------------------------------------------------------------- #


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _broker_name(broker) -> str:
    name = broker.__class__.__name__.lower()
    if "webull" in name:
        return "webull"
    if "ibkr" in name:
        return "ibkr"
    return getattr(broker, "broker", None) or "ibkr"


def _broker_account_id(broker) -> Optional[str]:
    account_id = getattr(broker, "_account_id", None)
    if account_id:
        return account_id
    try:
        health = broker.health()
    except Exception:  # noqa: BLE001 - account id is metadata
        return None
    account_id = health.get("account_id")
    if account_id:
        return account_id
    accounts = health.get("accounts") or []
    return accounts[0] if accounts else None


def _broker_for_account(broker, account_id: Optional[str]):
    if not account_id:
        return broker
    if getattr(broker, "_account_id", None) == account_id:
        return broker

    conn = getattr(broker, "_conn", None)
    if conn is not None and broker.__class__.__name__ == "IBKRBroker":
        from tradingbot.broker.ibkr import IBKRBroker

        return IBKRBroker(
            conn,
            account_id=account_id,
            paper=bool(getattr(broker, "_paper", True)),
        )

    client = getattr(broker, "_client", None)
    if client is not None and broker.__class__.__name__ == "WebullBroker":
        from tradingbot.broker.webull import WebullBroker

        return WebullBroker(
            client,
            account_id=account_id,
            region=str(getattr(broker, "_region", "us")),
            paper=bool(getattr(broker, "_paper", False)),
        )

    return broker


def _approval_resp(a) -> ApprovalResponse:
    return ApprovalResponse(
        approval_id=a.approval_id,
        run_id=a.run_id,
        ticker=a.ticker,
        side=a.side,
        order_type=a.order_type,
        quantity=a.quantity,
        limit_price=a.limit_price,
        time_in_force=a.time_in_force,
        estimated_price=a.estimated_price,
        estimated_value=a.estimated_value,
        whatif_init_margin=a.whatif_init_margin,
        whatif_commission=a.whatif_commission,
        risk_verdict=a.risk_verdict,
        agent_reasoning=a.agent_reasoning,
        proposal_report=a.proposal_report,
        status=a.status,
        requested_by_user_id=a.requested_by_user_id,
        approved_by_user_id=a.approved_by_user_id,
        submitted_order_id=a.submitted_order_id,
        error=a.error,
        created_at=_iso(a.created_at),
        updated_at=_iso(a.updated_at),
    )


def _order_resp(o) -> OrderResponse:
    return OrderResponse(
        broker_order_id=o.broker_order_id,
        account_id=o.account_id,
        broker=o.broker,
        ticker=o.ticker,
        side=o.side,
        order_type=o.order_type,
        quantity=o.quantity,
        status=o.status,
        filled_qty=o.filled_qty,
        filled_avg_price=o.filled_avg_price,
        limit_price=o.limit_price,
        approval_id=o.approval_id,
        submitted_at=_iso(o.submitted_at),
        updated_at=_iso(o.updated_at),
    )


# --------------------------------------------------------------------------- #
# Status / account / positions (read-only)                                    #
# --------------------------------------------------------------------------- #


@router.get("/status", response_model=BrokerStatusResponse)
def broker_status(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    config: dict = Depends(get_config),
    svc: BrokerConnectionService = Depends(get_connection_service),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    from tradingagents.api.broker_provider import status_for

    return BrokerStatusResponse(**status_for(session, user, config, svc, repo))


@router.get("/account", response_model=AccountResponse)
def broker_account(account_id: Optional[str] = None, broker=Depends(get_broker)):
    acct = _broker_for_account(broker, account_id).get_account()
    return AccountResponse(
        cash=acct.cash,
        portfolio_value=acct.portfolio_value,
        buying_power=acct.buying_power,
        equity=acct.equity,
    )


@router.get("/positions", response_model=list[PositionResponse])
def broker_positions(account_id: Optional[str] = None, broker=Depends(get_broker)):
    return [
        PositionResponse(
            ticker=p.ticker,
            qty=p.qty,
            avg_entry_price=p.avg_entry_price,
            current_price=p.current_price,
            market_value=p.market_value,
            unrealized_pnl=p.unrealized_pnl,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
            side=p.side,
        )
        for p in _broker_for_account(broker, account_id).get_positions()
    ]


# --------------------------------------------------------------------------- #
# Orders (mirror reads + trader actions)                                      #
# --------------------------------------------------------------------------- #


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    account_id: Optional[str] = None,
    broker: Optional[str] = None,
    repo: BrokerRepository = Depends(get_broker_repo),
):
    return [_order_resp(o) for o in repo.list_orders(account_id=account_id, broker=broker)]


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, repo: BrokerRepository = Depends(get_broker_repo)):
    order = repo.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return _order_resp(order)


@router.post("/orders/preview", response_model=PreviewResponse)
def preview_order(
    body: PreviewRequest,
    _user: User = Depends(require_role(*_TRADER_ROLES)),
    broker=Depends(get_broker),
):
    try:
        out = broker.preview_order(
            body.ticker,
            body.qty,
            OrderSide(body.side),
            OrderType(body.order_type),
            body.limit_price,
            body.time_in_force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PreviewResponse(**out)


@router.post("/orders", response_model=OrderResponse, status_code=201)
def place_order(
    body: PlaceOrderRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
    broker=Depends(get_broker),
):
    try:
        order = broker.submit_order(
            body.ticker,
            body.qty,
            OrderSide(body.side),
            OrderType(body.order_type),
            body.limit_price,
            body.time_in_force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    account_id = _broker_account_id(broker)
    broker_name = _broker_name(broker)

    mirrored = repo.upsert_order(
        broker_order_id=order.order_id,
        ticker=order.ticker,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=order.qty,
        status=order.status.value,
        approval_id=None,
        requested_by_user_id=user.user_id,
        account_id=account_id,
        broker=broker_name,
        limit_price=order.limit_price,
        filled_qty=order.filled_qty,
        filled_avg_price=order.filled_avg_price,
    )
    session.commit()
    return _order_resp(mirrored)


@router.post("/orders/{order_id}/cancel", response_model=CancelResponse)
def cancel_order(
    order_id: str,
    session: Session = Depends(get_db_session),
    _user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
    broker=Depends(get_broker),
):
    cancelled = broker.cancel_order(order_id)
    if cancelled:
        existing = repo.get_order(order_id)
        if existing is not None:
            repo.upsert_order(
                broker_order_id=order_id,
                ticker=existing.ticker,
                side=existing.side,
                order_type=existing.order_type,
                quantity=existing.quantity,
                status="cancelled",
                approval_id=existing.approval_id,
                requested_by_user_id=existing.requested_by_user_id,
                account_id=existing.account_id,
                broker=existing.broker,
                limit_price=existing.limit_price,
                filled_qty=existing.filled_qty,
                filled_avg_price=existing.filled_avg_price,
            )
            session.commit()
    return CancelResponse(cancelled=cancelled)


# --------------------------------------------------------------------------- #
# Approvals workflow                                                          #
# --------------------------------------------------------------------------- #


@router.get("/approvals", response_model=list[ApprovalResponse])
def list_approvals(
    status: Optional[str] = None,
    repo: BrokerRepository = Depends(get_broker_repo),
):
    return [_approval_resp(a) for a in repo.list_approvals(status=status)]


@router.post("/approvals", response_model=ApprovalResponse, status_code=201)
def create_proposal(
    body: CreateProposalRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
    builder: TradeProposalBuilder = Depends(get_proposal_builder),
):
    run_repo = AnalysisRunRepository(
        session, user_id=None if user.role == "admin" else user.user_id
    )
    run = run_repo.get_run(body.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "succeeded":
        raise HTTPException(status_code=409, detail="run not completed")
    result = session.get(AnalysisRunResult, body.run_id)
    if result is None:
        raise HTTPException(status_code=409, detail="result not available")

    reasoning = ""
    if isinstance(result.final_state, dict):
        reasoning = str(result.final_state.get("final_trade_decision", "") or "")

    outcome = builder.build(
        repo=repo,
        requested_by_user_id=user.user_id,
        ticker=run.ticker,
        signal=result.decision,
        reasoning=reasoning,
        run_id=body.run_id,
    )
    if not outcome.created:
        raise HTTPException(status_code=422, detail=f"no proposal generated: {outcome.reason}")
    session.commit()
    return _approval_resp(outcome.approval)


@router.post("/approvals/{approval_id}/approve", response_model=ApproveResponse)
def approve_proposal(
    approval_id: str,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
    execution: TradeExecutionService = Depends(get_execution_service),
):
    try:
        repo.approve(approval_id, user.user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()

    result = execution.execute_approved(
        repo=repo,
        approval_id=approval_id,
        actor_user_id=user.user_id,
    )
    session.commit()
    return ApproveResponse(
        approval_id=approval_id,
        status=result.status,
        order_id=result.order_id,
        detail=result.detail,
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
def reject_proposal(
    approval_id: str,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    try:
        repo.reject(approval_id, user.user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _approval_resp(repo.require_approval(approval_id))


# --------------------------------------------------------------------------- #
# Local-execution bridge (desktop) — additive, no Redis/connector required     #
# --------------------------------------------------------------------------- #


@router.post("/local/proposals", response_model=ApprovalResponse, status_code=201)
def create_local_proposal(
    body: LocalProposalRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
    config: dict = Depends(get_config),
):
    """Build a proposal + risk verdict from the desktop's local account snapshot.

    Same machinery as ``POST /broker/approvals`` (SignalMapper + RiskGate +
    persisted approval), but the live inputs come from the snapshot instead of a
    server-side socket, so no Redis/connector is involved.
    """
    from tradingbot.broker.base import AccountInfo, Position
    from tradingbot.broker.signal_mapper import SignalMapper
    from tradingbot.broker.snapshot import SnapshotBroker
    from tradingbot.services.trade_proposal import _build_risk_gate

    run_repo = AnalysisRunRepository(
        session, user_id=None if user.role == "admin" else user.user_id
    )
    run = run_repo.get_run(body.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "succeeded":
        raise HTTPException(status_code=409, detail="run not completed")
    result = session.get(AnalysisRunResult, body.run_id)
    if result is None:
        raise HTTPException(status_code=409, detail="result not available")

    reasoning = ""
    if isinstance(result.final_state, dict):
        reasoning = str(result.final_state.get("final_trade_decision", "") or "")

    account = AccountInfo(
        cash=body.account.cash,
        portfolio_value=body.account.portfolio_value,
        buying_power=body.account.buying_power,
        equity=body.account.equity,
    )
    positions = [
        Position(
            ticker=p.ticker,
            qty=p.qty,
            avg_entry_price=p.avg_entry_price,
            current_price=p.current_price,
            market_value=p.market_value,
            unrealized_pnl=p.unrealized_pnl,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
            side=p.side,
        )
        for p in body.positions
    ]
    broker = SnapshotBroker(account, positions, {run.ticker.upper(): body.price})
    mapper = SignalMapper(
        full_position_pct=config.get("full_position_pct", 0.05),
        partial_position_pct=config.get("partial_position_pct", 0.03),
        partial_exit_pct=config.get("partial_exit_pct", 0.50),
    )
    builder = TradeProposalBuilder(broker, mapper, _build_risk_gate(config, broker))
    outcome = builder.build(
        repo=repo,
        requested_by_user_id=user.user_id,
        ticker=run.ticker,
        signal=result.decision,
        reasoning=reasoning,
        run_id=body.run_id,
    )
    if not outcome.created:
        raise HTTPException(status_code=422, detail=f"no proposal generated: {outcome.reason}")
    session.commit()
    return _approval_resp(outcome.approval)


@router.post("/approvals/{approval_id}/executed", response_model=ApproveResponse)
def record_local_execution(
    approval_id: str,
    body: ExecutedRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    """Record an order the local sidecar placed: approve (if pending), mirror the
    order, and mark the approval submitted. Idempotent on re-report."""
    approval = repo.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if approval.status == "pending":
        repo.approve(approval_id, user.user_id)
        session.flush()

    repo.upsert_order(
        broker_order_id=body.broker_order_id,
        ticker=approval.ticker,
        side=approval.side,
        order_type=approval.order_type,
        quantity=approval.quantity,
        status=body.status,
        approval_id=approval_id,
        requested_by_user_id=approval.requested_by_user_id,
        account_id=body.account_id,
        broker=body.broker,
        limit_price=body.limit_price if body.limit_price is not None else approval.limit_price,
        filled_qty=body.filled_qty,
        filled_avg_price=body.filled_avg_price,
    )
    try:
        repo.mark_submitted(approval_id, body.broker_order_id)
    except ValueError:
        pass  # already submitted — idempotent re-report
    session.commit()
    return ApproveResponse(
        approval_id=approval_id,
        status="submitted",
        order_id=body.broker_order_id,
        detail="recorded local execution",
    )


@router.post("/orders/manual", response_model=OrderResponse)
def record_manual_order(
    body: ManualOrderRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    """Mirror a manually-placed order (no approval) so it shows in the order list
    and per-account analytics. The desktop sidecar places it on the local TWS;
    this records it on the server, scoped to the user + account."""
    repo.upsert_order(
        broker_order_id=body.broker_order_id,
        ticker=body.ticker,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        status=body.status,
        approval_id=None,
        requested_by_user_id=user.user_id,
        account_id=body.account_id,
        broker=body.broker,
        limit_price=body.limit_price,
        filled_qty=body.filled_qty,
        filled_avg_price=body.filled_avg_price,
    )
    session.commit()
    return _order_resp(repo.get_order(body.broker_order_id))


@router.post("/orders/{order_id}/status", response_model=OrderResponse)
def update_local_order_status(
    order_id: str,
    body: OrderStatusRequest,
    session: Session = Depends(get_db_session),
    _user: User = Depends(require_role(*_TRADER_ROLES)),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    """Apply a fill/status update from the local sidecar to the order mirror."""
    existing = repo.get_order(order_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="order not found")
    repo.upsert_order(
        broker_order_id=order_id,
        ticker=existing.ticker,
        side=existing.side,
        order_type=existing.order_type,
        quantity=existing.quantity,
        status=body.status,
        approval_id=existing.approval_id,
        requested_by_user_id=existing.requested_by_user_id,
        account_id=existing.account_id,
        broker=existing.broker,
        limit_price=existing.limit_price,
        filled_qty=body.filled_qty,
        filled_avg_price=body.filled_avg_price,
    )
    session.commit()
    return _order_resp(repo.get_order(order_id))


# --------------------------------------------------------------------------- #
# Portfolio analytics — server-side, scoped to (user, account, broker)         #
# Trade history + realised P&L derive from broker_orders; equity curve / Sharpe #
# / drawdown from pushed portfolio_snapshots. No local DB.                      #
# --------------------------------------------------------------------------- #


@router.post("/snapshot")
def push_snapshot(
    body: SnapshotRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Desktop pushes the live account equity; one row per (user, account, day)."""
    from tradingagents.api.portfolio_repository import PortfolioRepository

    if not body.account_id:
        raise HTTPException(status_code=422, detail="account_id required")
    repo = PortfolioRepository(session, user.user_id, body.account_id, body.broker)
    repo.upsert_snapshot(
        cash=body.cash,
        invested_value=body.invested_value,
        total_value=body.total_value,
        open_positions=body.open_positions,
    )
    session.commit()
    return {"ok": True}


@router.get("/performance")
def get_performance(
    account_id: str,
    broker: str = "ibkr",
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    from tradingagents.api import portfolio_analytics
    from tradingagents.api.portfolio_repository import PortfolioRepository

    repo = PortfolioRepository(session, user.user_id, account_id, broker)
    orders = repo.filled_orders()
    snaps = repo.list_snapshots()
    current = snaps[-1].total_value if snaps else None
    return portfolio_analytics.performance(orders, snaps, current_equity=current)


@router.get("/trades")
def get_trades(
    account_id: str,
    broker: str = "ibkr",
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    from tradingagents.api import portfolio_analytics
    from tradingagents.api.portfolio_repository import PortfolioRepository

    repo = PortfolioRepository(session, user.user_id, account_id, broker)
    orders = repo.filled_orders()
    return {
        "trades": portfolio_analytics.trade_rows(orders),
        "closed": portfolio_analytics.closed_positions(orders),
    }


@router.post("/refresh", response_model=BrokerStatusResponse)
def refresh_status(
    user: User = Depends(require_role(*_TRADER_ROLES)),
    session: Session = Depends(get_db_session),
    config: dict = Depends(get_config),
    broker=Depends(get_broker),
    svc: BrokerConnectionService = Depends(get_connection_service),
    repo: BrokerRepository = Depends(get_broker_repo),
):
    try:
        broker.health()  # proxies to the connector; keeps the session warm
    except Exception:  # noqa: BLE001 - status still reflects the DB mirror
        pass
    from tradingagents.api.broker_provider import status_for

    return BrokerStatusResponse(**status_for(session, user, config, svc, repo))
