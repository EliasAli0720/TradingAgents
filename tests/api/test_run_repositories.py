import math
import sqlite3

import pytest

from tradingagents.api.db import connect
from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import AuditRepository, RunEventRepository, RunRepository


def test_run_repository_creates_run_and_events(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))
    events = RunEventRepository(str(db_path))

    run = runs.create_run(
        ticker="SPY",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )
    events.append(run["id"], "agent_status", {"agent": "Market Analyst", "status": "running"})
    runs.update_status(run["id"], "running")

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])

    assert loaded["ticker"] == "SPY"
    assert loaded["status"] == "running"
    assert replay[0]["type"] == "agent_status"
    assert replay[0]["payload"]["agent"] == "Market Analyst"


def test_run_event_repository_lists_events_after_event_id(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))
    events = RunEventRepository(str(db_path))
    run = runs.create_run(
        ticker="SPY",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )

    first = events.append(run["id"], "agent_status", {"step": 1})
    second = events.append(run["id"], "agent_status", {"step": 2})
    third = events.append(run["id"], "agent_status", {"step": 3})

    replay = events.list_for_run(run["id"])
    resumed = events.list_for_run(run["id"], after_event_id=first["event_id"])

    assert [event["event_id"] for event in replay] == [
        first["event_id"],
        second["event_id"],
        third["event_id"],
    ]
    assert [event["event_id"] for event in resumed] == [second["event_id"], third["event_id"]]


def test_run_event_repository_returns_empty_for_unknown_or_cross_run_cursor(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))
    events = RunEventRepository(str(db_path))
    first_run = runs.create_run(
        ticker="SPY",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )
    second_run = runs.create_run(
        ticker="QQQ",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )

    first_event = events.append(first_run["id"], "agent_status", {"step": 1})
    second_event = events.append(first_run["id"], "agent_status", {"step": 2})
    cross_run_event = events.append(second_run["id"], "agent_status", {"step": "other-run"})

    assert events.list_for_run(first_run["id"], after_event_id="evt_missing") == []
    assert events.list_for_run(first_run["id"], after_event_id=cross_run_event["event_id"]) == []
    assert events.list_for_run(first_run["id"], after_event_id=second_event["event_id"]) == []
    assert events.list_for_run(first_run["id"], after_event_id=first_event["event_id"]) == [second_event]


def test_run_event_repository_rejects_orphan_events(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    events = RunEventRepository(str(db_path))

    with pytest.raises(sqlite3.IntegrityError):
        events.append("run_missing", "agent_status", {"step": 1})


def test_connect_enables_foreign_keys_for_every_connection(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))

    with connect(str(db_path)) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_repositories_reject_non_strict_json(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))
    events = RunEventRepository(str(db_path))

    with pytest.raises(ValueError):
        runs.create_run(
            ticker="SPY",
            analysis_date="2026-05-19",
            asset_type="stock",
            config={"threshold": math.nan},
        )

    run = runs.create_run(
        ticker="SPY",
        analysis_date="2026-05-19",
        asset_type="stock",
        config={"llm_provider": "openai"},
    )
    with pytest.raises(ValueError):
        events.append(run["id"], "agent_status", {"score": math.inf})


def test_update_status_raises_key_error_for_missing_run(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    runs = RunRepository(str(db_path))

    with pytest.raises(KeyError):
        runs.update_status("run_missing", "running")


def test_audit_repository_records_mutations(tmp_path):
    db_path = tmp_path / "api.db"
    init_api_schema(str(db_path))
    audit = AuditRepository(str(db_path))

    entry = audit.record(
        action="manual_trade_requested",
        actor="session:test",
        target_type="trade",
        target_id="draft",
        payload={"ticker": "AAPL", "side": "buy"},
        outcome="accepted",
    )

    rows = audit.list_recent(limit=10)
    assert entry["id"] == rows[0]["id"]
    assert rows[0]["payload"]["ticker"] == "AAPL"
