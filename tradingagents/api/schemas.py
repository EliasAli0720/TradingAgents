from __future__ import annotations

from typing import Any, Literal

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


class CreateRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    asset_type: Literal["stock", "crypto"] = "stock"
    analysts: list[Literal["market", "social", "news", "fundamentals"]]
    research_depth: int = Field(ge=1, le=5)
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    checkpoint_enabled: bool = False


class RunResponse(BaseModel):
    id: str
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    config: dict[str, Any]
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class RunListResponse(BaseModel):
    runs: list[RunResponse]


class RunEventResponse(BaseModel):
    event_id: str
    run_id: str
    type: str
    timestamp: str
    payload: dict[str, Any]


class ApprovalDecisionRequest(BaseModel):
    confirmation: str = ""
    reason: str = ""


class ManualTradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    confirmation: str
