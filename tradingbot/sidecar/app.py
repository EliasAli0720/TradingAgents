"""FastAPI app for the local broker sidecar (loopback + bearer token).

Reuses the proven local broker stack: ``build_broker(config, mode="local")`` →
``LocalIBKRConnection`` (ib_async socket). ``ib_async`` must run on a single
thread that owns one asyncio event loop, so every broker call is marshalled to
a dedicated worker thread (the same constraint the Redis connector honours).

Endpoints (all but ``/ping`` require ``Authorization: Bearer <SIDECAR_TOKEN>``):
  GET  /ping        — unauthenticated liveness (supervisor readiness probe)
  GET  /health      — connection status (works whether connected or not)
  POST /connect     — (re)build the broker and open the socket
  POST /disconnect  — drop the socket
  GET  /account     — balances / buying power
  GET  /positions   — open positions
  GET  /orders      — recent order history

Order placement (preview/execute/cancel) is intentionally out of scope here —
it arrives with the P3 local-execution path.
"""

from __future__ import annotations

import os
import queue
import secrets
import socket
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from tradingbot.broker.factory import build_broker

# Overridable in tests so the worker can be driven with a fake/mock broker.
BUILD_BROKER: Callable[..., Any] = build_broker


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Well-known IBKR API endpoints, in default discovery order. The ``paper`` flag
# here is only a *hint* from the conventional port — the authoritative paper/live
# is derived from the connected account number (see ``_infer_paper``).
_DISCOVERY_CANDIDATES = [
    (7497, "tws", True),       # TWS paper
    (4002, "gateway", True),   # IB Gateway paper
    (7496, "tws", False),      # TWS live
    (4001, "gateway", False),  # IB Gateway live
]


def _port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    """Cheap TCP liveness probe — does not open an ib_async session."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _infer_paper(account_id: Optional[str], fallback: bool) -> bool:
    """IBKR account-number prefix is authoritative: ``DU``/``DF`` … = paper,
    ``U``/``F``/``I`` … = live. Fall back to the caller's hint when unknown."""
    if account_id:
        first = account_id.strip().upper()[:1]
        if first == "D":
            return True
        if first in ("U", "F", "I"):
            return False
    return fallback


def _account_list(primary: Optional[str], accounts: list) -> list[str]:
    out: list[str] = []
    for candidate in [primary, *accounts]:
        account_id = str(candidate or "").strip()
        if account_id and account_id not in out:
            out.append(account_id)
    return out


class ConnectRequest(BaseModel):
    broker: str = "ibkr"
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 0
    market_data_type: int = 3
    account_id: Optional[str] = None
    paper: bool = True


class DiscoverRequest(BaseModel):
    host: str = "127.0.0.1"


class QuoteRequest(BaseModel):
    ticker: str


class OrderRequest(BaseModel):
    ticker: str
    qty: int
    side: str  # "buy" | "sell"
    order_type: str = "market"
    limit_price: Optional[float] = None
    time_in_force: str = "day"


class BrokerWorker:
    """Owns the broker on one dedicated thread. FastAPI handlers submit
    callables here; the thread runs them serially against ib_async's loop."""

    def __init__(self) -> None:
        self._jobs: "queue.Queue" = queue.Queue()
        self._broker: Any = None
        self._conn: Any = None
        self._broker_name: str = "ibkr"
        self._account_id: Optional[str] = None
        self._paper: bool = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="broker-worker")
        self._thread.start()

    # -- thread plumbing -------------------------------------------------- #

    def _loop(self) -> None:
        import asyncio
        import queue as _queue

        # ib_async binds its IB() instance to this thread's event loop, so the
        # loop must be created here and every IB call must run on this thread.
        asyncio.set_event_loop(asyncio.new_event_loop())
        while True:
            try:
                job, fut = self._jobs.get(timeout=0.1)
            except _queue.Empty:
                # Pump ib_async between jobs so the socket reader keeps processing
                # incoming order/fill events + keepalives (mirrors the connector
                # loop). Without this the reader stalls while we block on get().
                conn = self._conn
                ib = getattr(conn, "_ib", None) if conn is not None else None
                if ib is not None:
                    try:
                        if ib.isConnected():
                            ib.sleep(0.05)
                    except Exception:  # noqa: BLE001
                        pass
                continue
            if job is None:  # shutdown sentinel
                return
            try:
                fut.set_result(job())
            except Exception as exc:  # noqa: BLE001 - propagate to the caller
                fut.set_exception(exc)

    def submit(self, fn: Callable[[], Any], timeout: float = 30.0) -> Any:
        fut: Future = Future()
        self._jobs.put((fn, fut))
        return fut.result(timeout=timeout)

    def _require(self) -> Any:
        if self._broker is None:
            raise RuntimeError("broker not connected")
        return self._broker

    def _broker_for_account(self, account_id: Optional[str]) -> Any:
        broker = self._require()
        if not account_id or getattr(broker, "_account_id", None) == account_id:
            return broker
        conn = getattr(broker, "_conn", None) or self._conn
        if conn is not None and self._broker_name.lower() == "ibkr":
            from tradingbot.broker.ibkr import IBKRBroker

            return IBKRBroker(conn, account_id=account_id, paper=self._paper)
        return broker

    # -- operations (always run on the worker thread) --------------------- #

    def connect(self, opts: ConnectRequest) -> dict:
        from tradingbot.config import TRADINGBOT_CONFIG

        cfg = dict(TRADINGBOT_CONFIG)
        cfg.update(
            broker=opts.broker,
            ibkr_host=opts.host,
            ibkr_port=opts.port,
            ibkr_client_id=opts.client_id,
            ibkr_market_data_type=opts.market_data_type,
            ibkr_account_id=opts.account_id or "",
            paper_trading=opts.paper,
        )
        broker = BUILD_BROKER(cfg, mode="local")
        conn = getattr(broker, "_conn", None)
        # IBKR opens the socket here; mock/alpaca have no connection to open.
        if conn is not None and hasattr(conn, "ensure_connected"):
            conn.ensure_connected()
        self._broker = broker
        self._conn = conn
        self._broker_name = opts.broker
        # One-click connect: when the caller doesn't pin an account, IBKR reports
        # the locally logged-in account(s) on the open socket — adopt the first.
        discovered = self._managed_accounts(conn)
        self._account_id = opts.account_id or (discovered[0] if discovered else None)
        self._paper = _infer_paper(self._account_id, opts.paper)
        return self.status()

    @staticmethod
    def _managed_accounts(conn) -> list:
        if conn is None or not hasattr(conn, "managed_accounts"):
            return []
        try:
            return [a for a in conn.managed_accounts() if a]
        except Exception:  # noqa: BLE001 - best effort; status() probes again
            return []

    def disconnect(self) -> dict:
        conn = self._conn
        try:
            ib = getattr(conn, "_ib", None)
            if ib is not None and ib.isConnected():
                ib.disconnect()
        except Exception:  # noqa: BLE001 - best effort
            pass
        self._broker = None
        self._conn = None
        return {"ok": True}

    def status(self) -> dict:
        if self._broker is None:
            online, accounts, last_error = False, [], None
        elif hasattr(self._broker, "health"):
            h = self._broker.health()
            online = bool(h.get("gateway_online", False))
            accounts = h.get("accounts") or []
            last_error = h.get("last_error")
        else:  # mock / brokers without a health() probe
            online, accounts, last_error = True, [], None
        accounts = _account_list(self._account_id, accounts)
        return {
            "broker": self._broker_name,
            "connected": online,
            "gateway_online": online,
            "brokerage_session": online,
            "account_id": self._account_id or (accounts[0] if accounts else None),
            "accounts": accounts,
            "paper": self._paper,
            "last_refresh_at": _now_iso(),
            "last_error": last_error,
        }

    def account(self, account_id: Optional[str] = None) -> dict:
        a = self._broker_for_account(account_id).get_account()
        return {
            "cash": a.cash,
            "portfolio_value": a.portfolio_value,
            "buying_power": a.buying_power,
            "equity": a.equity,
        }

    def positions(self, account_id: Optional[str] = None) -> list[dict]:
        return [
            {
                "ticker": p.ticker,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "current_price": p.current_price,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "side": p.side,
            }
            for p in self._broker_for_account(account_id).get_positions()
        ]

    def orders(self) -> list[dict]:
        out = []
        for o in self._require().get_order_history(100):
            out.append(self._order_dict(o))
        return out

    @staticmethod
    def _order_dict(o) -> dict:
        return {
            "broker_order_id": o.order_id,
            "ticker": o.ticker,
            "side": o.side.value,
            "order_type": o.order_type.value,
            "quantity": o.qty,
            "status": o.status.value,
            "filled_qty": o.filled_qty,
            "filled_avg_price": o.filled_avg_price,
            "limit_price": o.limit_price,
            "approval_id": None,
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
            "updated_at": None,
        }

    # -- execution (local placement against TWS) -------------------------- #

    def quote(self, ticker: str) -> dict:
        return {"ticker": ticker.upper(), "price": self._require().get_latest_price(ticker)}

    def preview(self, req: OrderRequest) -> dict:
        from tradingbot.broker.base import OrderSide, OrderType

        return self._require().preview_order(
            req.ticker,
            req.qty,
            OrderSide(req.side),
            OrderType(req.order_type),
            req.limit_price,
            req.time_in_force,
        )

    def execute(self, req: OrderRequest) -> dict:
        from tradingbot.broker.base import OrderSide, OrderType

        order = self._require().submit_order(
            req.ticker,
            req.qty,
            OrderSide(req.side),
            OrderType(req.order_type),
            req.limit_price,
            req.time_in_force,
        )
        return self._order_dict(order)

    def cancel(self, order_id: str) -> dict:
        return {"cancelled": bool(self._require().cancel_order(order_id))}


# --------------------------------------------------------------------------- #
# App                                                                         #
# --------------------------------------------------------------------------- #

app = FastAPI(title="TradingAgents broker sidecar", docs_url=None, redoc_url=None)
_worker = BrokerWorker()


def require_token(authorization: str = Header(default="")) -> None:
    token = os.environ.get("SIDECAR_TOKEN", "")
    if not token or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="unauthorized")


def _run(fn: Callable[[], Any]) -> Any:
    try:
        return _worker.submit(fn)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface broker/socket errors
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/ping")
def ping() -> dict:
    return {"ok": True}


@app.get("/health", dependencies=[Depends(require_token)])
def health() -> dict:
    return _run(_worker.status)


@app.post("/discover", dependencies=[Depends(require_token)])
def discover(body: DiscoverRequest) -> dict:
    """Scan well-known IBKR ports and return the ones currently listening, so the
    UI can offer a one-click connect (and let the user pick if several are up).
    Pure TCP probe — it neither opens an ib_async session nor needs the worker."""
    candidates = [
        {"host": body.host, "port": port, "kind": kind, "paper": paper}
        for port, kind, paper in _DISCOVERY_CANDIDATES
        if _port_open(body.host, port)
    ]
    return {"candidates": candidates}


@app.post("/connect", dependencies=[Depends(require_token)])
def connect(body: ConnectRequest) -> dict:
    return _run(lambda: _worker.connect(body))


@app.post("/disconnect", dependencies=[Depends(require_token)])
def disconnect() -> dict:
    return _run(_worker.disconnect)


@app.get("/account", dependencies=[Depends(require_token)])
def account(account_id: Optional[str] = None) -> dict:
    return _run(lambda: _worker.account(account_id))


@app.get("/positions", dependencies=[Depends(require_token)])
def positions(account_id: Optional[str] = None) -> list[dict]:
    return _run(lambda: _worker.positions(account_id))


@app.get("/orders", dependencies=[Depends(require_token)])
def orders() -> list[dict]:
    return _run(_worker.orders)


@app.post("/quote", dependencies=[Depends(require_token)])
def quote(body: QuoteRequest) -> dict:
    return _run(lambda: _worker.quote(body.ticker))


@app.post("/preview", dependencies=[Depends(require_token)])
def preview(body: OrderRequest) -> dict:
    return _run(lambda: _worker.preview(body))


@app.post("/execute", dependencies=[Depends(require_token)])
def execute(body: OrderRequest) -> dict:
    return _run(lambda: _worker.execute(body))


@app.post("/orders/{order_id}/cancel", dependencies=[Depends(require_token)])
def cancel_order(order_id: str) -> dict:
    return _run(lambda: _worker.cancel(order_id))
