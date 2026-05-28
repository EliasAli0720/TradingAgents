from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublishedRunEvent:
    run_id: str
    event_type: str
    payload: dict[str, Any]


class RunEventPublisher:
    def __init__(self, redis_client):
        self._redis = redis_client

    def publish(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "run_id": run_id,
            "event_type": event_type,
            "payload": payload,
        }
        self._redis.publish(f"run:{run_id}", json.dumps(message))


def parse_published_event(message: Any) -> PublishedRunEvent | None:
    data = message.get("data") if isinstance(message, dict) else message
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if not isinstance(data, str):
        return None
    parsed = json.loads(data)
    return PublishedRunEvent(
        run_id=parsed["run_id"],
        event_type=parsed["event_type"],
        payload=parsed["payload"],
    )
