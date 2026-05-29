"""Resolve the platform broker (server mode) and report connection status.

Single platform account: there is one IBKR connection (owned by the connector).
The web layer builds a Redis-proxied broker through here and reads status from
the ``broker_status`` mirror the connector keeps current.
"""

from __future__ import annotations

from typing import Any


class BrokerConnectionService:
    def __init__(self, config: dict, redis_client: Any):
        self._config = config
        self._redis = redis_client

    def build_broker(self):
        from tradingbot.broker.factory import build_broker

        cfg = dict(self._config)
        cfg["redis_client"] = self._redis
        return build_broker(cfg, mode="server")

    def status(self, repo) -> dict:
        """Connection status for /broker/status, read from the DB mirror."""
        paper = self._config.get("paper_trading", True)
        row = repo.get_status()
        if row is None:
            return {
                "broker": self._config.get("broker", "ibkr"),
                "connected": False,
                "gateway_online": False,
                "brokerage_session": False,
                "account_id": self._config.get("ibkr_account_id") or None,
                "paper": paper,
                "last_refresh_at": None,
                "last_error": "connector not running",
            }
        return {
            "broker": row.broker,
            "connected": bool(row.gateway_online and row.brokerage_session),
            "gateway_online": row.gateway_online,
            "brokerage_session": row.brokerage_session,
            "account_id": row.account_id,
            "paper": row.paper,
            "last_refresh_at": row.last_refresh_at.isoformat() if row.last_refresh_at else None,
            "last_error": row.last_error,
        }
