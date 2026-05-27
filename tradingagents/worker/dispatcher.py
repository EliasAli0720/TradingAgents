from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from tradingagents.api.repositories import AnalysisRunRepository, utcnow


@dataclass(frozen=True)
class DispatchConfig:
    system_running: int
    user_running: int
    lease_seconds: int


def dispatch_once(
    session: Session,
    enqueue: Callable[[str], str | None],
    config: DispatchConfig,
) -> int:
    repo = AnalysisRunRepository(session)
    capacity_left = config.system_running - repo.count_active_runs()
    if capacity_left <= 0:
        return 0

    dispatched = 0
    while dispatched < capacity_left:
        made_progress = False
        scan_limit = max(capacity_left * 2, 1)

        while dispatched < capacity_left:
            user_ids = repo.users_with_queued_runs(limit=scan_limit)
            if not user_ids:
                break

            for user_id in user_ids:
                if dispatched >= capacity_left:
                    break
                if repo.count_active_runs(user_id=user_id) >= config.user_running:
                    continue

                claim = session.begin_nested()
                try:
                    run = repo.claim_next_queued_for_dispatch(
                        user_id=user_id,
                        lease_expires_at=utcnow() + timedelta(seconds=config.lease_seconds),
                    )
                    if run is None:
                        claim.rollback()
                        continue

                    run_id = run.run_id
                    task_id = enqueue(run_id)
                    if not task_id:
                        claim.rollback()
                        session.expire_all()
                        raise RuntimeError(f"enqueue did not return a task id for run {run_id}")

                    repo.set_celery_task_id(run_id, task_id)
                except Exception:
                    if claim.is_active:
                        claim.rollback()
                        session.expire_all()
                    raise
                else:
                    claim.commit()

                dispatched += 1
                made_progress = True

            if made_progress or len(user_ids) < scan_limit:
                break
            scan_limit *= 2

        if not made_progress:
            break

    session.commit()
    return dispatched
