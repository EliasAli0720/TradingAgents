from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    redis_url: str
    task_time_limit_seconds: int = 3600


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
    )
