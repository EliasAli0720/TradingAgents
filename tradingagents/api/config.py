from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ApiConfig:
    api_token: str | None
    redis_url: str
    db_path: str
    results_dir: str
    cors_origins: tuple[str, ...]
    queue_enabled: bool = True

    @classmethod
    def from_env(cls) -> "ApiConfig":
        home = Path.home() / ".tradingagents"
        origins = os.getenv(
            "TRADINGAGENTS_API_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        return cls(
            api_token=os.getenv("TRADINGAGENTS_API_TOKEN") or None,
            redis_url=os.getenv("TRADINGAGENTS_REDIS_URL", "redis://localhost:6379/0"),
            db_path=os.getenv("TRADINGBOT_DB_PATH", str(home / "tradingbot.db")),
            results_dir=os.getenv("TRADINGAGENTS_RESULTS_DIR", str(home / "logs")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            queue_enabled=os.getenv("TRADINGAGENTS_QUEUE_ENABLED", "true").lower() != "false",
        )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_token)

    def provider_key_status(self, env_vars: Iterable[str]) -> dict[str, dict[str, bool]]:
        return {
            env_var: {"configured": bool(os.getenv(env_var))}
            for env_var in env_vars
        }
