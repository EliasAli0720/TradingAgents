from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


RunStatus = Literal[
    "queued",
    "dispatching",
    "running",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
]
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
    queue_position: int | None = None


class CancelRunResponse(BaseModel):
    run_id: str
    status: Literal["cancelled", "cancelling"]


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
    queue_position: Optional[int] = None


class RunResultResponse(BaseModel):
    run_id: str
    status: Literal["succeeded"]
    decision: str
    reports: dict[str, Any]
    # Per-language translations keyed by language code, e.g. {"zh": {...}}.
    # None until the translation task fills it; clients fall back to `reports`.
    reports_i18n: Optional[dict[str, Any]] = None
    final_state: dict[str, Any]
    created_at: datetime


class RunArtifactResponse(BaseModel):
    artifact_id: str
    kind: str
    content_type: Optional[str]
    size_bytes: int
    created_at: datetime


class CapacityResponse(BaseModel):
    max_running_system: int
    max_running_per_user: int
    max_queued_per_user: int
    running_system: int
    dispatching_system: int
    queued_system: int


class HealthResponse(BaseModel):
    status: str
    postgres: str
    redis: str


SUPPORTED_LLM_PROVIDERS = {
    "anthropic",
    "azure",
    "deepseek",
    "glm",
    "glm-cn",
    "google",
    "minimax",
    "minimax-cn",
    "ollama",
    "openai",
    "openrouter",
    "qwen",
    "qwen-cn",
    "xai",
}


class ModelSettingsRequest(BaseModel):
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: Optional[str] = None
    api_key: Optional[str] = None

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError("unsupported llm_provider")
        return provider

    @field_validator("deep_think_llm", "quick_think_llm")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("model id cannot be empty")
        return model

    @field_validator("backend_url")
    @classmethod
    def validate_backend_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        url = value.strip()
        if not url:
            return None
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("backend_url must start with http:// or https://")
        return url

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        api_key = value.strip()
        if not api_key:
            return None
        return api_key


class ModelSettingsResponse(BaseModel):
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: Optional[str]
    has_api_key: bool
    api_key_masked: Optional[str]


class ModelOptionResponse(BaseModel):
    id: str
    label: str


class ModelProviderOptionResponse(BaseModel):
    id: str
    label: str
    required_env_var: Optional[str]
    default_backend_url: Optional[str]
    backend_url_editable: bool
    supports_custom_model: bool
    quick_models: list[ModelOptionResponse]
    deep_models: list[ModelOptionResponse]


class ModelOptionsResponse(BaseModel):
    providers: list[ModelProviderOptionResponse]


class ModelSettingsValidationResponse(BaseModel):
    valid: bool
    provider: str
    required_env_var: Optional[str]
    api_key_source: Literal["user", "service", "none", "not_required"]
    message: str
    probe_status: Optional[
        Literal[
            "success",
            "invalid_api_key",
            "model_not_found",
            "endpoint_unreachable",
            "permission_denied",
            "timeout",
            "provider_error",
        ]
    ] = None
    probe_message: Optional[str] = None


class TranslationSettingsRequest(BaseModel):
    llm_provider: str
    model: str
    backend_url: Optional[str] = None
    api_key: Optional[str] = None

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("model")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("model id cannot be empty")
        return model

    @field_validator("backend_url")
    @classmethod
    def validate_backend_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        url = value.strip()
        if not url:
            return None
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("backend_url must start with http:// or https://")
        return url

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        api_key = value.strip()
        return api_key or None


class TranslationSettingsResponse(BaseModel):
    llm_provider: str
    model: str
    backend_url: Optional[str]
    has_api_key: bool
    api_key_masked: Optional[str]


class TranslationProviderOptionResponse(BaseModel):
    id: str
    label: str
    model_id: str
    model_label: str
    required_env_var: Optional[str]
    default_backend_url: Optional[str]
    backend_url_editable: bool


class TranslationOptionsResponse(BaseModel):
    providers: list[TranslationProviderOptionResponse]


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
    language: str = "zh"


class UpdatePreferencesRequest(BaseModel):
    language: Literal["zh", "en"]


class AdminUserResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole
    is_active: bool


class AdminUserPatch(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
