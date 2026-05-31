"""Central broker construction — one place that maps config -> BrokerAdapter.

``run_bot.py``, the Streamlit dashboard, the FastAPI layer and the IBKR
connector all build their broker through here, so broker selection lives in
exactly one spot. All concrete-broker imports are lazy so importing this
module never drags in optional broker SDKs (alpaca-py, ib_async).
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import BrokerAdapter


def build_broker(config: Mapping[str, Any], *, mode: str = "local") -> BrokerAdapter:
    """Construct the configured broker.

    Args:
        config: the tradingbot config mapping (see ``tradingbot/config.py``).
        mode: ``"local"`` builds a broker that talks to its backend directly
            (CLI / dashboard / the connector process itself). ``"server"``
            builds a broker that proxies to the single IBKR connector over
            Redis (FastAPI / Celery web processes) — only meaningful for ibkr,
            so web workers never open their own socket.

    Raises:
        ValueError: on an unknown broker type.
    """
    broker = str(config.get("broker", "mock")).lower()

    if broker == "mock":
        from .mock import MockBroker

        return MockBroker(starting_cash=float(config.get("starting_cash", 100_000.0)))

    if broker == "alpaca":
        from .alpaca import AlpacaBroker

        return AlpacaBroker(
            api_key=config["alpaca_api_key"],
            api_secret=config["alpaca_api_secret"],
            paper=config.get("paper_trading", True),
        )

    if broker == "ibkr":
        from .ibkr import IBKRBroker

        account_id = config.get("ibkr_account_id") or None
        paper = config.get("paper_trading", True)

        if mode == "server":
            # Web processes never open a socket — they proxy to the single
            # connector over Redis. The caller injects the redis client.
            redis_client = config.get("redis_client")
            if redis_client is None:
                raise ValueError(
                    "server-mode IBKR broker requires config['redis_client']"
                )
            from .ibkr_connection import RedisIBKRConnection

            conn = RedisIBKRConnection(
                redis_client,
                cmd_queue=config.get("ibkr_cmd_queue", "ibkr:commands"),
                reply_prefix=config.get("ibkr_reply_prefix", "ibkr:reply:"),
            )
            return IBKRBroker(conn, account_id=account_id, paper=paper)

        from .ibkr_connection import LocalIBKRConnection

        conn = LocalIBKRConnection(
            host=config.get("ibkr_host", "127.0.0.1"),
            port=int(config.get("ibkr_port", 7497)),
            client_id=int(config.get("ibkr_client_id", 0)),
            market_data_type=int(config.get("ibkr_market_data_type", 3)),
        )
        return IBKRBroker(conn, account_id=account_id, paper=paper)

    if broker == "webull":
        # Cloud REST (Connect API): stateless per request, so the same direct
        # build serves both modes — no Redis connector, unlike ibkr. Per-user
        # OAuth token + account id are injected through config by the provider.
        from .webull import WebullBroker
        from .webull_client import SdkWebullClient

        region = str(config.get("webull_region", "us"))
        paper = config.get("paper_trading", True)
        client = config.get("webull_client")  # injected in tests / by provider
        if client is None:
            client = SdkWebullClient(
                access_token=config.get("webull_access_token", ""),
                app_key=config.get("webull_app_key", ""),
                app_secret=config.get("webull_app_secret", ""),
                region=region,
                paper=paper,
                endpoint=config.get("webull_endpoint") or None,
                token_provider=config.get("webull_token_provider"),
            )
        return WebullBroker(
            client,
            account_id=config.get("webull_account_id") or "",
            region=region,
            paper=paper,
        )

    raise ValueError(f"Unknown broker type: {broker!r}")
