from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.schemas import CreateRunRequest, RunListResponse, RunResponse
from tradingagents.api.services.runs import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service(config: ApiConfig = Depends(get_config)) -> RunService:
    return RunService(config.db_path, redis_url=config.redis_url, queue_enabled=config.queue_enabled)


@router.post("", response_model=RunResponse, status_code=201)
def create_run(
    payload: CreateRunRequest,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.create_run(payload)


@router.get("", response_model=RunListResponse)
def list_runs(
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return {"runs": service.list_runs()}


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.get_run(run_id)


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: str,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> dict:
    return service.cancel_run(run_id)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    _: str = Depends(require_auth),
    service: RunService = Depends(get_run_service),
) -> Response:
    after_event_id = request.headers.get("Last-Event-ID")

    async def event_stream():
        sent: set[str] = set()
        while True:
            events = service.events.list_for_run(run_id, after_event_id=after_event_id)
            for event in events:
                if event["event_id"] in sent:
                    continue
                sent.add(event["event_id"])
                yield f"id: {event['event_id']}\n"
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event, allow_nan=False)}\n\n"
            run = service.get_run(run_id)
            if run["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
