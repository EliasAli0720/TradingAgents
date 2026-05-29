"""IBKR connector launcher — the single process that owns the ib_async socket.

Run exactly one of these alongside a logged-in TWS / IB Gateway. The FastAPI
and Celery processes never connect to IBKR directly; they talk to this process
over Redis (see tradingbot/broker/ibkr_commands.py).

Usage:
    # TWS paper on 7497 is the default (see tradingbot/config.py).
    python run_broker.py

Environment (see tradingbot/config.py): IBKR_HOST / IBKR_PORT / IBKR_CLIENT_ID /
IBKR_ACCOUNT_ID / IBKR_PAPER / IBKR_CMD_QUEUE, plus REDIS_URL and DATABASE_URL.
"""

import logging
import signal

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_broker")


def main():
    import redis as redis_lib

    from tradingagents.api.config import get_api_settings
    from tradingagents.api.db import SessionLocal
    from tradingbot.broker.ibkr_connector import build_connector_from_config
    from tradingbot.config import TRADINGBOT_CONFIG as config

    redis_client = redis_lib.Redis.from_url(get_api_settings().redis_url)
    connector = build_connector_from_config(config, redis_client, SessionLocal)

    def _graceful(*_a):
        logger.info("Stopping IBKR connector ...")
        connector.stop()

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    logger.info(
        "Launching IBKR connector (%s:%s, account=%s, paper=%s)",
        config.get("ibkr_host"),
        config.get("ibkr_port"),
        config.get("ibkr_account_id") or "<primary>",
        config.get("paper_trading"),
    )
    connector.start()


if __name__ == "__main__":
    main()
