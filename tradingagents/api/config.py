from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    redis_url: str
    task_time_limit_seconds: int = 3600
    session_ttl_days: int = 14
    session_cookie_name: str = "tradingagents_session"
    csrf_cookie_name: str = "tradingagents_csrf"
    cookie_secure: bool = True
    cookie_domain: Optional[str] = None
    login_rate_limit_per_min: int = 5


def get_api_settings() -> ApiSettings:
    database_url = os.environ.get("DATABASE_URL")
    environment = os.environ.get("TRADINGAGENTS_API_ENV", "development").lower()
    if environment in {"production", "prod"} and not database_url:
        raise RuntimeError("DATABASE_URL is required when TRADINGAGENTS_API_ENV=production")

    return ApiSettings(
        database_url=database_url or "sqlite+pysqlite:///./tradingagents_api.db",
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        task_time_limit_seconds=int(
            os.environ.get("TRADINGAGENTS_API_TASK_TIME_LIMIT_SECONDS", "3600")
        ),
        session_ttl_days=int(
            os.environ.get("TRADINGAGENTS_API_SESSION_TTL_DAYS", "14")
        ),
        session_cookie_name=os.environ.get(
            "TRADINGAGENTS_API_SESSION_COOKIE_NAME", "tradingagents_session"
        ),
        csrf_cookie_name=os.environ.get(
            "TRADINGAGENTS_API_CSRF_COOKIE_NAME", "tradingagents_csrf"
        ),
        cookie_secure=_env_bool("TRADINGAGENTS_API_COOKIE_SECURE", True),
        cookie_domain=os.environ.get("TRADINGAGENTS_API_COOKIE_DOMAIN") or None,
        login_rate_limit_per_min=int(
            os.environ.get("TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN", "5")
        ),
    )
