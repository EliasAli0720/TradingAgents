from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingagents.worker.cancellation import CancellationToken
from tradingagents.worker.provider_limits import ProviderLimiter


@dataclass(frozen=True)
class RunContext:
    run_id: str
    user_id: str
    memory_store: Any | None = None
    cancellation_token: CancellationToken | None = None
    provider_limiter: ProviderLimiter | None = None
