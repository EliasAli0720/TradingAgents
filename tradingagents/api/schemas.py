from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    token: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    authenticated: bool


class KeyStatus(BaseModel):
    configured: bool


class SettingsResponse(BaseModel):
    auth_enabled: bool
    broker: str
    paper_trading: bool
    db_path: str
    results_dir: str
    provider_keys: dict[str, KeyStatus]
    watchlist: list[str]
    risk_limits: dict[str, float]
    scheduler: dict[str, str]
