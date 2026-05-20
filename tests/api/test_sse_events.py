from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import RunEventRepository, RunRepository


def test_event_repository_replays_after_last_event(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run("SPY", "2026-05-19", "stock", {})

    first = events.append(run["id"], "message", {"text": "one"})
    second = events.append(run["id"], "message", {"text": "two"})

    replay = events.list_for_run(run["id"], after_event_id=first["event_id"])

    assert [event["event_id"] for event in replay] == [second["event_id"]]


def test_sse_route_replays_persisted_events(tmp_path):
    db_path = str(tmp_path / "api.db")
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=db_path,
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    client = TestClient(create_app(config))
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run("SPY", "2026-05-19", "stock", {})
    event = events.append(run["id"], "message", {"text": "one"})
    runs.update_status(run["id"], "completed")

    with client.stream(
        "GET",
        f"/api/runs/{run['id']}/events",
        headers={"Authorization": "Bearer test-token"},
    ) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"id: {event['event_id']}" in body
    assert "event: message" in body
    assert '"text": "one"' in body
