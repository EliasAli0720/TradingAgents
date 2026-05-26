from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun, AnalysisRunEvent, AnalysisRunResult


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
        result = self.session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.run_id == run_id, AnalysisRun.status == "queued")
            .values(status="running", started_at=now, current_step="Analysis running")
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None

        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
        return self.require_run(run_id)

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
        if run.status == "cancelled":
            return run
        if run.status in {"succeeded", "failed"}:
            raise ValueError(f"Cannot cancel terminal run {run_id}")

        run.status = "cancelled"
        run.finished_at = utcnow()
        run.current_step = "Cancelled"
        run.error = reason
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
