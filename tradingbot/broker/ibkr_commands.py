"""Command protocol between the web processes and the single IBKR connector.

Because the TWS API is one stateful socket with a single brokerage session,
exactly one process (the connector) may hold the ``ib_async`` connection. Every
other process (FastAPI, Celery) talks to it through a Redis request/reply
channel modelled here:

- A :class:`Command` is pushed (RPUSH) onto the command queue.
- The connector pops it, runs :func:`dispatch_command` against its live
  :class:`LocalIBKRConnection`, and pushes a :class:`Response` onto a per-command
  reply list (``reply_prefix + command.id``) that the caller BLPOPs.

Value objects cross the wire as plain JSON via :func:`encode_result` /
:func:`decode_result`, so neither side needs ib_async types.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Optional

from .ibkr_connection import AccountValue, Quote, RawOrder, RawPosition, WhatIfResult


class IBKRConnectorError(RuntimeError):
    """The connector reported a failure executing a command."""


class IBKRConnectorTimeout(RuntimeError):
    """No reply arrived from the connector within the timeout."""


# Supported command methods (mirror IBKRConnection).
METHODS = (
    "ensure_connected",
    "managed_accounts",
    "account_summary",
    "positions",
    "quote",
    "what_if",
    "place",
    "cancel",
    "order",
    "open_orders",
    "recent_orders",
    "health",
)


@dataclass
class Command:
    id: str
    method: str
    params: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"id": self.id, "method": self.method, "params": self.params})

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Command":
        data = json.loads(raw)
        return cls(id=data["id"], method=data["method"], params=data.get("params") or {})


@dataclass
class Response:
    id: str
    ok: bool
    result: Any = None
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {"id": self.id, "ok": self.ok, "result": self.result, "error": self.error}
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Response":
        data = json.loads(raw)
        return cls(
            id=data["id"],
            ok=data["ok"],
            result=data.get("result"),
            error=data.get("error"),
        )


def encode_result(obj: Any) -> Any:
    """Recursively convert dataclasses / datetimes to JSON-safe values."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [encode_result(x) for x in obj]
    if isinstance(obj, dict):
        return {k: encode_result(v) for k, v in obj.items()}
    if is_dataclass(obj):
        return {f.name: encode_result(getattr(obj, f.name)) for f in fields(obj)}
    return obj


def _raw_order(d: dict) -> RawOrder:
    d = dict(d)
    sa = d.get("submitted_at")
    d["submitted_at"] = datetime.fromisoformat(sa) if isinstance(sa, str) else None
    return RawOrder(**d)


def decode_result(method: str, payload: Any) -> Any:
    """Rebuild typed objects from the JSON payload for a given method."""
    if method == "account_summary":
        return [AccountValue(**d) for d in payload]
    if method == "positions":
        return [RawPosition(**d) for d in payload]
    if method == "quote":
        return Quote(**payload)
    if method == "what_if":
        return WhatIfResult(**payload)
    if method == "place":
        return _raw_order(payload)
    if method == "order":
        return _raw_order(payload) if payload is not None else None
    if method in ("open_orders", "recent_orders"):
        return [_raw_order(d) for d in payload]
    # managed_accounts (list), cancel (bool), health (dict), ensure_connected (None)
    return payload


def dispatch_command(conn, command: Command) -> Response:
    """Execute *command* against a live IBKRConnection, returning a Response.

    Pure mapping (no Redis), so it is unit-testable with a fake connection.
    """
    method = command.method
    params = command.params or {}
    try:
        if method == "ensure_connected":
            conn.ensure_connected()
            result: Any = None
        elif method == "managed_accounts":
            result = conn.managed_accounts()
        elif method == "account_summary":
            result = conn.account_summary(params.get("account_id"))
        elif method == "positions":
            result = conn.positions(params.get("account_id"))
        elif method == "quote":
            result = conn.quote(params["symbol"])
        elif method == "what_if":
            result = conn.what_if(**params)
        elif method == "place":
            result = conn.place(**params)
        elif method == "cancel":
            result = conn.cancel(params["order_id"])
        elif method == "order":
            result = conn.order(params["order_id"])
        elif method == "open_orders":
            result = conn.open_orders()
        elif method == "recent_orders":
            result = conn.recent_orders(params.get("limit", 100))
        elif method == "health":
            result = conn.health()
        else:
            return Response(command.id, ok=False, error=f"unknown method {method!r}")
        return Response(command.id, ok=True, result=encode_result(result))
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as ok=False
        return Response(command.id, ok=False, error=f"{type(exc).__name__}: {exc}")
