from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun
from tradingagents.api.repositories import AnalysisRunRepository, utcnow


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def sweep_once(session: Session, stale_after_seconds: int) -> int:
    repo = AnalysisRunRepository(session)
    now = utcnow()
    repaired = 0

    expired_dispatching = session.scalars(
        select(AnalysisRun).where(
            AnalysisRun.status == "dispatching",
            AnalysisRun.lease_expires_at.is_not(None),
            AnalysisRun.lease_expires_at < now,
        )
    )
    for run in expired_dispatching:
        if repo.requeue_run(run.run_id, "dispatch lease expired") is not None:
            repaired += 1

    cutoff = now - timedelta(seconds=stale_after_seconds)
    running_candidates = session.scalars(
        select(AnalysisRun).where(AnalysisRun.status.in_(("running", "cancelling")))
    )
    for run in running_candidates:
        last_seen_at = _as_aware(
            run.heartbeat_at or run.started_at or run.updated_at or run.created_at
        )
        if last_seen_at >= cutoff:
            continue
        if run.attempt_count >= run.max_attempts:
            if repo.fail_run(run.run_id, "worker heartbeat stale") is not None:
                repaired += 1
        elif repo.requeue_run(run.run_id, "worker heartbeat stale") is not None:
            repaired += 1

    session.commit()
    return repaired
