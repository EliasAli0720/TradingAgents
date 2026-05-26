from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


RunStatus = Literal["queued", "running", "succeeded", "failed"]
AssetType = Literal["stock", "crypto"]
AnalystKey = Literal["market", "social", "news", "fundamentals"]

_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")


class CreateRunRequest(BaseModel):
    ticker: str
    trade_date: date
    asset_type: AssetType = "stock"
    analysts: list[AnalystKey] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"],
    )

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not _TICKER_RE.match(ticker):
            raise ValueError("ticker must be 1-32 chars using A-Z, 0-9, '.', '_', '-', '^'")
        return ticker

    @field_validator("trade_date")
    @classmethod
    def reject_future_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("trade_date cannot be in the future")
        return value

    @field_validator("analysts")
    @classmethod
    def require_analysts(cls, value: list[AnalystKey]) -> list[AnalystKey]:
        if not value:
            raise ValueError("at least one analyst is required")
        if len(value) != len(set(value)):
            raise ValueError("analysts must be unique")
        return value

    @model_validator(mode="after")
    def reject_crypto_fundamentals(self):
        if self.asset_type == "crypto" and "fundamentals" in self.analysts:
            raise ValueError("fundamentals analyst is not supported for crypto assets")
        return self


class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatus
    ticker: str
    trade_date: date
    asset_type: AssetType
    analysts: list[AnalystKey]
    current_step: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]


class RunResultResponse(BaseModel):
    run_id: str
    status: Literal["succeeded"]
    decision: str
    reports: dict[str, Any]
    final_state: dict[str, Any]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    postgres: str
    redis: str


UserRole = Literal["admin", "operator", "viewer"]


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole


class AdminUserResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole
    is_active: bool


class AdminUserPatch(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
