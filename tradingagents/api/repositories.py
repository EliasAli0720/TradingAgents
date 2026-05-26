from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.models import AnalysisRun, AnalysisRunEvent, AnalysisRunResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id() -> str:
    return f"run_{uuid4().hex}"


class AnalysisRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(
        self,
        ticker: str,
        trade_date: date,
        asset_type: str,
        analysts: list[str],
    ) -> AnalysisRun:
        now = utcnow()
        run = AnalysisRun(
            run_id=new_run_id(),
            status="queued",
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            analysts=analysts,
            current_step=None,
            celery_task_id=None,
            error=None,
            created_at=now,
        )
        self.session.add(run)
        self.add_event(run.run_id, "run_queued", {"run_id": run.run_id, "status": "queued"})
        return run

    def get_run(self, run_id: str) -> Optional[AnalysisRun]:
        return self.session.get(AnalysisRun, run_id)

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
        run.status = "running"
        run.started_at = utcnow()
        run.current_step = "Analysis running"
        self.add_event(run_id, "run_started", {"run_id": run_id, "status": "running"})
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
        result = AnalysisRunResult(
            run_id=run_id,
            decision=decision,
            reports=reports,
            final_state=final_state,
            created_at=now,
        )
        self.session.merge(result)
        run.status = "succeeded"
        run.finished_at = now
        run.current_step = "Completed"
        run.error = None
        self.add_event(run_id, "run_succeeded", {"run_id": run_id, "decision": decision})
        return result

    def store_failure(self, run_id: str, error: str) -> None:
        run = self.require_run(run_id)
        run.status = "failed"
        run.finished_at = utcnow()
        run.current_step = "Failed"
        run.error = error
        self.add_event(run_id, "run_failed", {"run_id": run_id, "error": error})

    def get_result(self, run_id: str) -> Optional[AnalysisRunResult]:
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
