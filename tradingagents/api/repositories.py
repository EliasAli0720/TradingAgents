from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from tradingagents.api.db import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _decode_json_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    decoded = dict(row)
    for field in fields:
        if field in decoded and decoded[field] is not None:
            decoded[field.removesuffix("_json")] = json.loads(decoded.pop(field))
    return decoded


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, allow_nan=False)


class RunRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_run(
        self,
        ticker: str,
        analysis_date: str,
        asset_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs
                    (id, ticker, analysis_date, asset_type, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ticker.upper(), analysis_date, asset_type, _json_dumps(config), "queued", now, now),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _decode_json_fields(_row_to_dict(row), ("config_json", "result_json"))

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM analysis_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_decode_json_fields(_row_to_dict(row), ("config_json", "result_json")) for row in rows]

    def update_status(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        result_json = _json_dumps(result) if result is not None else None
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE analysis_runs
                SET status = ?, error = COALESCE(?, error), result_json = COALESCE(?, result_json), updated_at = ?
                WHERE id = ?
                """,
                (status, error, result_json, now, run_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(run_id)
        return self.get_run(run_id)


class RunEventRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = f"evt_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO run_events (id, run_id, type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, run_id, event_type, _json_dumps(payload), now),
            )
        return {"event_id": event_id, "run_id": run_id, "type": event_type, "timestamp": now, "payload": payload}

    def list_for_run(self, run_id: str, after_event_id: str | None = None) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY created_at ASC, rowid ASC",
                (run_id,),
            ).fetchall()
        events = [
            {
                "event_id": row["id"],
                "run_id": row["run_id"],
                "type": row["type"],
                "timestamp": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
        if after_event_id is None:
            return events
        ids = [event["event_id"] for event in events]
        if after_event_id not in ids:
            return []
        return events[ids.index(after_event_id) + 1 :]


class AuditRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def record(
        self,
        action: str,
        actor: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
        outcome: str,
    ) -> dict[str, Any]:
        audit_id = f"aud_{uuid.uuid4().hex}"
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                    (id, action, actor, target_type, target_id, payload_json, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, action, actor, target_type, target_id, _json_dumps(payload), outcome, now),
            )
        return {
            "id": audit_id,
            "action": action,
            "actor": actor,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
            "outcome": outcome,
            "created_at": now,
        }

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_decode_json_fields(_row_to_dict(row), ("payload_json",)) for row in rows]


class ApprovalRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def create(
        self,
        run_id: str | None,
        ticker: str,
        signal: str,
        side: str,
        quantity: float,
        estimated_price: float,
        reasoning: str,
    ) -> dict[str, Any]:
        approval_id = f"appr_{uuid.uuid4().hex}"
        now = utc_now()
        estimated_value = quantity * estimated_price
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO approvals
                    (id, run_id, ticker, signal, side, quantity, estimated_price, estimated_value,
                     reasoning, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    run_id,
                    ticker.upper(),
                    signal,
                    side,
                    quantity,
                    estimated_price,
                    estimated_value,
                    reasoning,
                    "pending",
                    now,
                    now,
                ),
            )
        return self.get(approval_id)

    def get(self, approval_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return _row_to_dict(row)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC, rowid DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC, rowid DESC").fetchall()
        return [_row_to_dict(row) for row in rows]

    def approve(self, approval_id: str, confirmation: str, actor: str) -> dict[str, Any]:
        approval = self.get(approval_id)
        expected = f"APPROVE {approval['ticker']}"
        if confirmation.strip().upper() != expected:
            raise ValueError(f"Confirmation must be exactly {expected}")
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = 'approved', updated_at = ?, decided_at = ?, decision_reason = ?
                WHERE id = ?
                """,
                (now, now, f"approved by {actor}", approval_id),
            )
        return self.get(approval_id)

    def reject(self, approval_id: str, reason: str, actor: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = 'rejected', updated_at = ?, decided_at = ?, decision_reason = ?
                WHERE id = ?
                """,
                (now, now, f"{actor}: {reason}", approval_id),
            )
        return self.get(approval_id)
