"""The single IBKR connector process — owner of the one ib_async socket.

It does two jobs on one thread:

1. **Command server** — pop :class:`Command`s off the Redis queue, run them
   against its live :class:`LocalIBKRConnection` via
   :func:`tradingbot.broker.ibkr_commands.dispatch_command`, and push the reply.
2. **Event mirror** — subscribe to ib_async order/exec events and upsert the
   ``broker_orders`` mirror + refresh ``broker_status`` so the API can read
   state straight from the DB.

Both run on ib_async's event loop: when the command queue is empty we call
``ib.sleep`` so order-status callbacks get processed. Exactly one instance must
run (it holds the only brokerage session). Launch via ``run_broker.py``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .ibkr_commands import Command, dispatch_command
from .ibkr_connection import LocalIBKRConnection

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IBKRConnector:
    def __init__(
        self,
        conn: LocalIBKRConnection,
        redis_client,
        session_factory: Callable[[], Any],
        *,
        cmd_queue: str = "ibkr:commands",
        reply_prefix: str = "ibkr:reply:",
        account_id: Optional[str] = None,
        paper: bool = True,
        poll_interval: float = 0.1,
        status_interval: float = 30.0,
        reply_ttl: int = 60,
    ):
        self._conn = conn
        self._redis = redis_client
        self._session_factory = session_factory
        self._queue = cmd_queue
        self._reply_prefix = reply_prefix
        self._account_id = account_id
        self._paper = paper
        self._poll_interval = poll_interval
        self._status_interval = status_interval
        self._reply_ttl = reply_ttl
        self._running = False

    # -- DB mirror -------------------------------------------------------- #

    def _record_trade(self, trade) -> None:
        try:
            raw = self._conn._trade_to_raw(trade)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to convert trade for mirror")
            return
        try:
            from tradingagents.api.broker_repository import BrokerRepository

            with self._session_factory() as session:
                BrokerRepository(session).upsert_order(
                    broker_order_id=raw.order_id,
                    ticker=raw.symbol,
                    side=raw.side,
                    order_type=raw.order_type,
                    quantity=raw.quantity,
                    status=raw.status,
                    account_id=self._account_id,
                    conid=raw.conid,
                    limit_price=raw.limit_price,
                    time_in_force=raw.time_in_force,
                    filled_qty=raw.filled_qty,
                    filled_avg_price=raw.avg_fill_price,
                    raw_event={"status": raw.status, "filled": raw.filled_qty},
                )
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mirror order %s", raw.order_id)

    def _refresh_status(self, error: Optional[str] = None) -> None:
        health = self._conn.health()
        accounts = health.get("accounts") or []
        online = bool(health.get("gateway_online"))
        try:
            from tradingagents.api.broker_repository import BrokerRepository

            with self._session_factory() as session:
                BrokerRepository(session).upsert_status(
                    broker="ibkr",
                    gateway_online=online,
                    brokerage_session=online,
                    account_id=self._account_id or (accounts[0] if accounts else None),
                    paper=self._paper,
                    last_refresh_at=_now(),
                    last_error=error or health.get("last_error"),
                )
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to refresh broker status")

    # -- event handlers --------------------------------------------------- #

    def _on_order_status(self, trade) -> None:
        self._record_trade(trade)

    def _on_exec_details(self, trade, fill=None) -> None:
        self._record_trade(trade)

    # -- command handling ------------------------------------------------- #

    def _handle_raw_command(self, raw: str | bytes) -> None:
        try:
            command = Command.from_json(raw)
        except Exception:  # noqa: BLE001
            logger.exception("Discarding malformed command: %r", raw)
            return
        response = dispatch_command(self._conn, command)
        reply_key = self._reply_prefix + command.id
        self._redis.rpush(reply_key, response.to_json())
        self._redis.expire(reply_key, self._reply_ttl)

    # -- run loop --------------------------------------------------------- #

    def start(self) -> None:
        self._conn.ensure_connected()
        ib = self._conn._client()
        ib.orderStatusEvent += self._on_order_status
        ib.execDetailsEvent += self._on_exec_details
        self._refresh_status()
        self._running = True
        last_status = time.monotonic()
        logger.info("IBKR connector running; consuming %r", self._queue)
        while self._running:
            raw = self._redis.lpop(self._queue)
            if raw:
                self._handle_raw_command(raw)
            else:
                # Let ib_async process incoming events while idle.
                ib.sleep(self._poll_interval)
            if time.monotonic() - last_status > self._status_interval:
                self._refresh_status()
                last_status = time.monotonic()

    def stop(self) -> None:
        self._running = False


def build_connector_from_config(config, redis_client, session_factory) -> IBKRConnector:
    conn = LocalIBKRConnection(
        host=config.get("ibkr_host", "127.0.0.1"),
        port=int(config.get("ibkr_port", 7497)),
        client_id=int(config.get("ibkr_client_id", 0)),
        market_data_type=int(config.get("ibkr_market_data_type", 3)),
    )
    return IBKRConnector(
        conn,
        redis_client,
        session_factory,
        cmd_queue=config.get("ibkr_cmd_queue", "ibkr:commands"),
        account_id=config.get("ibkr_account_id") or None,
        paper=config.get("paper_trading", True),
    )
