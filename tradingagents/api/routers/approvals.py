from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.repositories import ApprovalRepository, AuditRepository
from tradingagents.api.schemas import ApprovalDecisionRequest

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    status: str | None = None,
    _: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    return {"approvals": ApprovalRepository(config.db_path).list(status=status)}


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    approvals = ApprovalRepository(config.db_path)
    audit = AuditRepository(config.db_path)
    try:
        approval = approvals.approve(approval_id, payload.confirmation, actor)
    except ValueError as exc:
        audit.record("approval_failed", actor, "approval", approval_id, {"reason": str(exc)}, "rejected")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record("approval_approved", actor, "approval", approval_id, {"ticker": approval["ticker"]}, "accepted")
    return approval


@router.post("/{approval_id}/reject")
def reject(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    approval = ApprovalRepository(config.db_path).reject(approval_id, payload.reason, actor)
    AuditRepository(config.db_path).record(
        "approval_rejected",
        actor,
        "approval",
        approval_id,
        {"reason": payload.reason},
        "accepted",
    )
    return approval
