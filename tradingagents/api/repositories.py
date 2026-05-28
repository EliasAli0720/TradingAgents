from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from dataclasses import asdict, is_dataclass
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from tradingagents.api.models import (
    AnalysisRun,
    AnalysisRunArtifact,
    AnalysisRunEvent,
    AnalysisRunResult,
)


ACTIVE_STATUSES = {"dispatching", "running"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id() -> str:
    return f"run_{uuid4().hex}"


class AnalysisRunRepository:
    def __init__(self, session: Session, user_id: Optional[str] = None):
        self.session = session
        self.user_id = user_id

    def create_run(
        self,
        ticker: str,
        trade_date: date,
        asset_type: str,
        analysts: list[str],
        user_id: Optional[str] = None,
        llm_config: Optional[dict[str, Any]] = None,
    ) -> AnalysisRun:
        effective_user_id = user_id or self.user_id or "__system__"
        now = utcnow()
        run = AnalysisRun(
            run_id=new_run_id(),
            status="queued",
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            analysts=analysts,
            user_id=effective_user_id,
            llm_config=llm_config,
            current_step=None,
            celery_task_id=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(run)
        self.add_event(run.run_id, "run_queued", {"run_id": run.run_id, "status": "queued"})
        return run

    def get_run(self, run_id: str) -> Optional[AnalysisRun]:
        stmt = select(AnalysisRun).where(AnalysisRun.run_id == run_id)
        if self.user_id is not None:
            stmt = stmt.where(AnalysisRun.user_id == self.user_id)
        return self.session.scalar(stmt)

    def set_celery_task_id(self, run_id: str, task_id: str) -> None:
        run = self.require_run(run_id)
        run.celery_task_id = task_id

    def count_active_runs(self, user_id: Optional[str] = None) -> int:
        stmt = (
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.status.in_(ACTIVE_STATUSES))
        )
        if user_id is not None:
            stmt = stmt.where(AnalysisRun.user_id == user_id)
        elif self.user_id is not None:
            stmt = stmt.where(AnalysisRun.user_id == self.user_id)

        return int(self.session.scalar(stmt) or 0)

    def users_with_queued_runs(self, limit: int) -> list[str]:
        if limit <= 0:
            return []

        ranked = (
            select(
                AnalysisRun.user_id.label("user_id"),
                AnalysisRun.priority.label("priority"),
                AnalysisRun.created_at.label("created_at"),
                AnalysisRun.run_id.label("run_id"),
                func.row_number()
                .over(
                    partition_by=AnalysisRun.user_id,
                    order_by=(
                        AnalysisRun.priority.desc(),
                        AnalysisRun.created_at.asc(),
                        AnalysisRun.run_id.asc(),
                    ),
                )
                .label("queue_rank"),
            )
            .where(AnalysisRun.status == "queued")
            .subquery()
        )
        stmt = (
            select(ranked.c.user_id)
            .where(ranked.c.queue_rank == 1)
            .order_by(
                ranked.c.priority.desc(),
                ranked.c.created_at.asc(),
                ranked.c.run_id.asc(),
            )
            .limit(limit)
        )
        if self.user_id is not None:
            stmt = stmt.where(ranked.c.user_id == self.user_id)

        return list(self.session.scalars(stmt))

    def claim_next_queued_for_dispatch(
        self, user_id: str, lease_expires_at: datetime
    ) -> Optional[AnalysisRun]:
        if self.user_id is not None and user_id != self.user_id:
            return None

        now = utcnow()
        candidate_id = self.session.scalar(
            select(AnalysisRun.run_id)
            .where(AnalysisRun.user_id == user_id, AnalysisRun.status == "queued")
            .order_by(
                AnalysisRun.priority.desc(),
                AnalysisRun.created_at.asc(),
                AnalysisRun.run_id.asc(),
            )
            .limit(1)
        )
        if candidate_id is None:
            return None

        result = self.session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.run_id == candidate_id,
                AnalysisRun.user_id == user_id,
                AnalysisRun.status == "queued",
            )
            .values(
                status="dispatching",
                dispatched_at=now,
                lease_expires_at=lease_expires_at,
                updated_at=now,
                current_step="Dispatching analysis",
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None

        self.add_event(
            candidate_id,
            "run_dispatching",
            {"run_id": candidate_id, "status": "dispatching"},
        )
        return self.require_run(candidate_id)

    def list_runs_for_user(self, user_id: str) -> list[AnalysisRun]:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.user_id == user_id)
            .order_by(AnalysisRun.created_at.asc(), AnalysisRun.run_id.asc())
        )
        return list(self.session.scalars(stmt))

    def queue_position(self, run_id: str) -> Optional[int]:
        run = self.get_run(run_id)
        if run is None or run.status != "queued":
            return None

        stmt = (
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.status == "queued",
                or_(
                    AnalysisRun.priority > run.priority,
                    and_(
                        AnalysisRun.priority == run.priority,
                        AnalysisRun.created_at < run.created_at,
                    ),
                    and_(
                        AnalysisRun.priority == run.priority,
                        AnalysisRun.created_at == run.created_at,
                        AnalysisRun.run_id <= run.run_id,
                    ),
                ),
            )
        )
        if self.user_id is not None:
            stmt = stmt.where(AnalysisRun.user_id == self.user_id)

        return int(self.session.scalar(stmt) or 0)

    def require_run(self, run_id: str) -> AnalysisRun:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def mark_running(self, run_id: str) -> AnalysisRun:
        run = self.require_run(run_id)
        if run.status == "running":
            return run
        if run.status == "cancelled":
            raise ValueError(f"Cannot mark cancelled run {run_id} as running")
        if run.status in TERMINAL_STATUSES:
            raise ValueError(f"Cannot mark terminal run {run_id} as running")

        run.status = "running"
        run.started_at = utcnow()
        run.current_step = "Analysis running"
        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
        return run

    def claim_queued_run(self, run_id: str) -> Optional[AnalysisRun]:
        now = utcnow()
        conditions = [
            AnalysisRun.run_id == run_id,
            AnalysisRun.status.in_(("queued", "dispatching")),
        ]
        if self.user_id is not None:
            conditions.append(AnalysisRun.user_id == self.user_id)

        result = self.session.execute(
            update(AnalysisRun)
            .where(*conditions)
            .values(
                status="running",
                started_at=now,
                current_step="Analysis running",
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None

        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
        return self.require_run(run_id)

    def start_dispatched_run(self, run_id: str) -> Optional[AnalysisRun]:
        now = utcnow()
        conditions = [AnalysisRun.run_id == run_id, AnalysisRun.status == "dispatching"]
        if self.user_id is not None:
            conditions.append(AnalysisRun.user_id == self.user_id)

        result = self.session.execute(
            update(AnalysisRun)
            .where(*conditions)
            .values(
                status="running",
                started_at=now,
                heartbeat_at=now,
                current_step="Analysis running",
                attempt_count=AnalysisRun.attempt_count + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None

        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
        return self.require_run(run_id)

    def record_heartbeat(self, run_id: str) -> Optional[AnalysisRun]:
        run = self.get_run(run_id)
        if run is None or run.status != "running":
            return run
        now = utcnow()
        run.heartbeat_at = now
        run.updated_at = now
        return run

    def requeue_run(self, run_id: str, reason: str) -> Optional[AnalysisRun]:
        run = self.get_run(run_id)
        if run is None or run.status in TERMINAL_STATUSES:
            return run
        now = utcnow()
        run.status = "queued"
        run.celery_task_id = None
        run.dispatched_at = None
        run.heartbeat_at = None
        run.lease_expires_at = None
        run.started_at = None
        run.current_step = "Queued for retry"
        run.error = None
        run.updated_at = now
        self.add_event(run_id, "run_requeued", {"run_id": run_id, "reason": reason})
        return run

    def fail_run(self, run_id: str, error: str) -> Optional[AnalysisRun]:
        run = self.get_run(run_id)
        if run is None:
            return None
        if run.status in {"succeeded", "cancelled"}:
            raise ValueError(f"Cannot mark {run.status} run {run_id} as failed")

        now = utcnow()
        run.status = "failed"
        run.finished_at = now
        run.current_step = "Failed"
        run.error = error
        run.updated_at = now
        self.add_event(run_id, "run_failed", {"run_id": run_id, "error": error})
        return run

    def add_artifact(self, run_id: str, artifact: Any) -> AnalysisRunArtifact:
        if is_dataclass(artifact):
            data = asdict(artifact)
        else:
            data = dict(artifact)

        now = utcnow()
        row = AnalysisRunArtifact(
            artifact_id=new_run_id().replace("run_", "art_", 1),
            run_id=run_id,
            kind=data["kind"],
            storage_backend=data.get("storage_backend", "local"),
            storage_key=data["storage_key"],
            content_type=data.get("content_type"),
            size_bytes=int(data.get("size_bytes") or 0),
            sha256=data.get("sha256"),
            created_at=now,
        )
        self.session.add(row)
        return row

    def list_artifacts(self, run_id: str) -> list[AnalysisRunArtifact]:
        if self.user_id is not None and self.get_run(run_id) is None:
            return []
        stmt = (
            select(AnalysisRunArtifact)
            .where(AnalysisRunArtifact.run_id == run_id)
            .order_by(AnalysisRunArtifact.created_at.asc(), AnalysisRunArtifact.artifact_id.asc())
        )
        return list(self.session.scalars(stmt))

    def record_progress(
        self,
        run_id: str,
        *,
        phase: str,
        step: str,
        percent: int,
        message: str,
    ) -> AnalysisRun:
        run = self.require_run(run_id)
        if run.status not in {"queued", "running"}:
            return run
        run.current_step = step
        self.add_event(
            run_id,
            "run_progress",
            {
                "run_id": run_id,
                "phase": phase,
                "step": step,
                "percent": percent,
                "message": message,
            },
        )
        return run

    def store_success(
        self,
        run_id: str,
        decision: str,
        reports: dict[str, Any],
        final_state: dict[str, Any],
    ) -> AnalysisRunResult:
        now = utcnow()
        run = self.require_run(run_id)
        if run.status == "succeeded":
            result = self.get_result(run_id)
            if result is not None:
                return result
        if run.status in {"failed", "cancelled"}:
            raise ValueError(f"Cannot mark {run.status} run {run_id} as succeeded")

        result = AnalysisRunResult(
            run_id=run_id,
            decision=decision,
            reports=reports,
            final_state=final_state,
            created_at=now,
        )
        persistent_result = self.session.merge(result)
        run.status = "succeeded"
        run.finished_at = now
        run.current_step = "Completed"
        run.error = None
        self.add_event(run_id, "run_succeeded", {"run_id": run_id, "decision": decision})
        return persistent_result

    def store_failure(self, run_id: str, error: str) -> None:
        run = self.require_run(run_id)
        if run.status == "failed":
            return
        if run.status in {"succeeded", "cancelled"}:
            raise ValueError(f"Cannot mark {run.status} run {run_id} as failed")

        run.status = "failed"
        run.finished_at = utcnow()
        run.current_step = "Failed"
        run.error = error
        self.add_event(run_id, "run_failed", {"run_id": run_id, "error": error})

    def cancel_run(self, run_id: str, reason: str = "run cancelled") -> AnalysisRun:
        run = self.require_run(run_id)
        if run.status in {"cancelled", "cancelling"}:
            return run
        if run.status in {"succeeded", "failed"}:
            raise ValueError(f"Cannot cancel terminal run {run_id}")

        now = utcnow()
        if run.status in {"running", "dispatching"}:
            run.status = "cancelling"
            run.current_step = "Cancelling"
            run.error = reason
            run.updated_at = now
            self.add_event(run_id, "run_cancelling", {"run_id": run_id, "reason": reason})
            return run

        run.status = "cancelled"
        run.finished_at = now
        run.current_step = "Cancelled"
        run.error = reason
        run.updated_at = now
        self.add_event(run_id, "run_cancelled", {"run_id": run_id, "reason": reason})
        return run

    def mark_cancelled(self, run_id: str, reason: str = "run cancelled") -> AnalysisRun:
        run = self.require_run(run_id)
        if run.status == "cancelled":
            return run
        if run.status in {"succeeded", "failed"}:
            raise ValueError(f"Cannot cancel terminal run {run_id}")

        now = utcnow()
        run.status = "cancelled"
        run.finished_at = now
        run.current_step = "Cancelled"
        run.error = reason
        run.updated_at = now
        self.add_event(run_id, "run_cancelled", {"run_id": run_id, "reason": reason})
        return run

    def get_result(self, run_id: str) -> Optional[AnalysisRunResult]:
        if self.user_id is not None and self.get_run(run_id) is None:
            return None
        return self.session.get(AnalysisRunResult, run_id)

    def add_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> AnalysisRunEvent:
        event = AnalysisRunEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at=utcnow(),
        )
        self.session.add(event)
        return event

    def list_events(self, run_id: str, after_id: int = 0) -> list[AnalysisRunEvent]:
        stmt = (
            select(AnalysisRunEvent)
            .where(AnalysisRunEvent.run_id == run_id, AnalysisRunEvent.id > after_id)
            .order_by(AnalysisRunEvent.id.asc())
        )
        return list(self.session.scalars(stmt))
