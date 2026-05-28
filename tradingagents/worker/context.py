from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunContext:
    run_id: str
    user_id: str
    memory_store: Any | None = None
