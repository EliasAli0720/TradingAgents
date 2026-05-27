from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun


ACTIVE = ("dispatching", "running")
BACKLOG = ("queued", "dispatching", "running")


@dataclass(frozen=True)
class CapacityConfig:
    system_running: int
    user_running: int
    user_backlog: int


@dataclass(frozen=True)
class CapacitySnapshot:
    system_active: int
    user_active: int
    user_backlog: int
    can_create: bool


def capacity_snapshot(
    session: Session,
    user_id: str,
    config: CapacityConfig,
) -> CapacitySnapshot:
    system_active = session.scalar(
        select(func.count())
        .select_from(AnalysisRun)
        .where(AnalysisRun.status.in_(ACTIVE))
    )
    user_active = session.scalar(
        select(func.count())
        .select_from(AnalysisRun)
        .where(AnalysisRun.user_id == user_id, AnalysisRun.status.in_(ACTIVE))
    )
    user_backlog = session.scalar(
        select(func.count())
        .select_from(AnalysisRun)
        .where(AnalysisRun.user_id == user_id, AnalysisRun.status.in_(BACKLOG))
    )
    user_backlog = int(user_backlog or 0)

    return CapacitySnapshot(
        system_active=int(system_active or 0),
        user_active=int(user_active or 0),
        user_backlog=user_backlog,
        can_create=user_backlog < config.user_backlog + config.user_running,
    )
