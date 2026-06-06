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


def _default_cookie_secure() -> bool:
    env = os.environ.get("TRADINGAGENTS_API_ENV", "production").strip().lower()
    return env not in {"development", "dev", "local", "test"}


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    redis_url: str
    model_api_key_encryption_key: Optional[str] = None
    task_time_limit_seconds: int = 3600
    session_ttl_days: int = 14
    session_cookie_name: str = "tradingagents_session"
    csrf_cookie_name: str = "tradingagents_csrf"
    cookie_secure: bool = True
    cookie_domain: Optional[str] = None
    login_rate_limit_per_min: int = 5
    max_running_system: int = 100
    max_running_per_user: int = 5
    max_queued_per_user: int = 50
    dispatch_interval_seconds: int = 1
    run_lease_seconds: int = 600
    worker_heartbeat_seconds: int = 10
    worker_stale_after_seconds: int = 90


def get_api_settings() -> ApiSettings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Use a PostgreSQL URL such as "
            "postgresql+psycopg://user:password@host:5432/tradingagents"
        )

    return ApiSettings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        model_api_key_encryption_key=os.environ.get("MODEL_API_KEY_ENCRYPTION_KEY") or None,
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
        cookie_secure=_env_bool(
            "TRADINGAGENTS_API_COOKIE_SECURE", _default_cookie_secure()
        ),
        cookie_domain=os.environ.get("TRADINGAGENTS_API_COOKIE_DOMAIN") or None,
        login_rate_limit_per_min=int(
            os.environ.get("TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN", "5")
        ),
        max_running_system=int(os.environ.get("TRADINGAGENTS_MAX_RUNNING_SYSTEM", "100")),
        max_running_per_user=int(os.environ.get("TRADINGAGENTS_MAX_RUNNING_PER_USER", "5")),
        max_queued_per_user=int(os.environ.get("TRADINGAGENTS_MAX_QUEUED_PER_USER", "50")),
        dispatch_interval_seconds=int(
            os.environ.get("TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS", "1")
        ),
        run_lease_seconds=int(os.environ.get("TRADINGAGENTS_RUN_LEASE_SECONDS", "600")),
        worker_heartbeat_seconds=int(
            os.environ.get("TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS", "10")
        ),
        worker_stale_after_seconds=int(
            os.environ.get("TRADINGAGENTS_WORKER_STALE_AFTER_SECONDS", "90")
        ),
    )
