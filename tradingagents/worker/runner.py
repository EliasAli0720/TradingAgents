from __future__ import annotations

from redis import Redis
from rq import Worker

from tradingagents.api.config import ApiConfig
from tradingagents.worker.queue import DEFAULT_QUEUE_NAME


def main() -> None:
    config = ApiConfig.from_env()
    connection = Redis.from_url(config.redis_url)
    worker = Worker([DEFAULT_QUEUE_NAME], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
