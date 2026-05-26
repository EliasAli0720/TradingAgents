from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from tradingagents.api.deps import get_db_session, get_stream_session_factory, get_task_enqueue
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    RunResultResponse,
    RunStatusResponse,
)


router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: CreateRunRequest,
    session: Session = Depends(get_db_session),
    enqueue=Depends(get_task_enqueue),
):
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker=request.ticker,
        trade_date=request.trade_date,
        asset_type=request.asset_type,
        analysts=list(request.analysts),
    )
    session.commit()
    try:
        task_id = enqueue(run.run_id)
    except Exception as exc:
        repo.store_failure(run.run_id, str(exc))
        session.commit()
        raise
    repo.set_celery_task_id(run.run_id, task_id)
    session.commit()
    return CreateRunResponse(run_id=run.run_id, status="queued")


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, session: Session = Depends(get_db_session)):
    repo = AnalysisRunRepository(session)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/result", response_model=RunResultResponse)
def get_result(run_id: str, session: Session = Depends(get_db_session)):
    repo = AnalysisRunRepository(session)
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
    session: Session = Depends(get_db_session),
    stream_session_factory=Depends(get_stream_session_factory),
):
    repo = AnalysisRunRepository(session)
    if repo.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def event_generator():
        last_id = 0
        terminal = False
        while not terminal:
            with stream_session_factory() as stream_session:
                stream_repo = AnalysisRunRepository(stream_session)
                events = stream_repo.list_events(run_id, after_id=last_id)
                for event in events:
                    last_id = event.id
                    yield f"event: {event.event_type}\n"
                    yield f"data: {json.dumps(event.payload)}\n\n"
                    if event.event_type in {"run_succeeded", "run_failed"}:
                        terminal = True
            if not terminal:
                await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
