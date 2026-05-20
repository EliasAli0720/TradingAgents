from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.schemas import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, config: ApiConfig = Depends(get_config)) -> LoginResponse:
    if config.auth_enabled and payload.token != config.api_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return LoginResponse(access_token=payload.token)


@router.get("/me", response_model=MeResponse)
def me(_: str = Depends(require_auth)) -> MeResponse:
    return MeResponse(authenticated=True)
