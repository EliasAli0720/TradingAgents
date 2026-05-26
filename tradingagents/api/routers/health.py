from __future__ import annotations

from fastapi import APIRouter

from tradingagents.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", postgres="ok", redis="ok")
