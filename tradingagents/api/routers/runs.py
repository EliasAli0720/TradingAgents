from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.capacity import CapacityConfig, capacity_snapshot
from tradingagents.api.config import get_api_settings
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.deps import (
    get_current_user,
    get_db_session,
    get_scoped_repository,
    get_stream_session_factory,
    get_task_revoke,
    require_role,
)
from tradingagents.api.models import User
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.schemas import (
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunResultResponse,
    RunStatusResponse,
)


router = APIRouter(prefix="/runs", tags=["runs"])


def _user_capacity_lock_stmt(user_id: str):
    return select(User.user_id).where(User.user_id == user_id).with_for_update()


def _lock_user_for_capacity(session: Session, user_id: str) -> None:
    session.execute(_user_capacity_lock_stmt(user_id)).scalar_one()


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: CreateRunRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(require_role("admin", "operator")),
):
    llm_config = UserModelSettingsRepository(session).snapshot(user.user_id)
    if llm_config is None:
        raise HTTPException(status_code=409, detail="model settings not configured")

    settings = get_api_settings()
    _lock_user_for_capacity(session, user.user_id)
    capacity = capacity_snapshot(
        session,
        user.user_id,
        CapacityConfig(
            system_running=settings.max_running_system,
            user_running=settings.max_running_per_user,
            user_backlog=settings.max_queued_per_user,
        ),
    )
    if not capacity.can_create:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many queued analysis runs",
        )

    repo = AnalysisRunRepository(session, user_id=user.user_id)
    run = repo.create_run(
        ticker=request.ticker,
        trade_date=request.trade_date,
        asset_type=request.asset_type,
        analysts=list(request.analysts),
        user_id=user.user_id,
        llm_config=llm_config,
    )
    session.commit()
    return CreateRunResponse(
        run_id=run.run_id,
        status="queued",
        queue_position=repo.queue_position(run.run_id),
    )


@router.post("/{run_id}/cancel", response_model=CancelRunResponse)
def cancel_run(
    run_id: str,
    repo: AnalysisRunRepository = Depends(get_scoped_repository),
    revoke=Depends(get_task_revoke),
    _user: User = Depends(require_role("admin", "operator")),
):
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status in {"succeeded", "failed"}:
        raise HTTPException(status_code=409, detail=f"run is already {run.status}")

    task_id = run.celery_task_id
    try:
        cancelled = repo.cancel_run(run_id, "user requested cancellation")
        repo.session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if task_id:
        revoke(task_id)
    return CancelRunResponse(run_id=cancelled.run_id, status=cancelled.status)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    repo: AnalysisRunRepository = Depends(get_scoped_repository),
):
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/result", response_model=RunResultResponse)
def get_result(
    run_id: str,
    repo: AnalysisRunRepository = Depends(get_scoped_repository),
):
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status == "failed":
        raise HTTPException(status_code=409, detail=run.error or "run failed")
    if run.status != "succeeded":
        raise HTTPException(status_code=409, detail="run not completed")
    result = repo.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=409, detail="result not available")
    return RunResultResponse(
        run_id=run_id,
        status="succeeded",
        decision=result.decision,
        reports=result.reports,
        final_state=result.final_state,
        created_at=result.created_at,
    )


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    user: User = Depends(get_current_user),
    stream_session_factory=Depends(get_stream_session_factory),
):
    scope_user_id = None if user.role == "admin" else user.user_id

    # Handshake-time existence + ownership check.
    with stream_session_factory() as stream_session:
        repo = AnalysisRunRepository(stream_session, user_id=scope_user_id)
        if repo.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")

    async def event_generator():
        last_id = 0
        terminal = False
        while not terminal:
            with stream_session_factory() as stream_session:
                stream_repo = AnalysisRunRepository(
                    stream_session, user_id=scope_user_id
                )
                # Re-verify run is still accessible to this user; if it vanished
                # (e.g. user was demoted off owner scope mid-stream) just close.
                if stream_repo.get_run(run_id) is None:
                    terminal = True
                    break
                events = stream_repo.list_events(run_id, after_id=last_id)
                for event in events:
                    last_id = event.id
                    yield f"event: {event.event_type}\n"
                    yield f"data: {json.dumps(event.payload)}\n\n"
                    if event.event_type in {
                        "run_succeeded",
                        "run_failed",
                        "run_cancelled",
                    }:
                        terminal = True
            if not terminal:
                await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
