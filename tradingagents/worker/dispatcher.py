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

                run = repo.claim_next_queued_for_dispatch(
                    user_id=user_id,
                    lease_expires_at=utcnow() + timedelta(seconds=config.lease_seconds),
                )
                if run is None:
                    continue

                run_id = run.run_id
                # Commit the "dispatching" status BEFORE enqueuing. Otherwise a
                # fast worker can run start_dispatched_run before this row is
                # visible, find status still "queued", no-op, and leave the run
                # wedged in "dispatching" forever. Committing first closes that
                # race; if the subsequent enqueue fails the sweeper requeues the
                # run on lease expiry — the same recovery path as a lost task.
                session.commit()

                task_id = enqueue(run_id)
                if not task_id:
                    # Enqueue failed: put the run straight back to queued (instead
                    # of stranding it in dispatching until the lease expires) and
                    # surface the error.
                    repo.requeue_run(run_id, "enqueue returned no task id")
                    session.commit()
                    raise RuntimeError(f"enqueue did not return a task id for run {run_id}")
                repo.set_celery_task_id(run_id, task_id)
                session.commit()

                dispatched += 1
                made_progress = True

            if made_progress or len(user_ids) < scan_limit:
                break
            scan_limit *= 2

        if not made_progress:
            break

    session.commit()
    return dispatched
