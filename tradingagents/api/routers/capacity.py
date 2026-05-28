from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingagents.api.config import get_api_settings
from tradingagents.api.deps import get_db_session, require_role
from tradingagents.api.models import AnalysisRun, User
from tradingagents.api.schemas import CapacityResponse


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/capacity", response_model=CapacityResponse)
def get_capacity(
    session: Session = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
):
    settings = get_api_settings()
    return CapacityResponse(
        max_running_system=settings.max_running_system,
        max_running_per_user=settings.max_running_per_user,
        max_queued_per_user=settings.max_queued_per_user,
        running_system=_count_runs(session, "running"),
        dispatching_system=_count_runs(session, "dispatching"),
        queued_system=_count_runs(session, "queued"),
    )


def _count_runs(session: Session, status: str) -> int:
    stmt = select(func.count()).select_from(AnalysisRun).where(AnalysisRun.status == status)
    return int(session.scalar(stmt) or 0)
