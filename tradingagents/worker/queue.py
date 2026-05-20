from __future__ import annotations

from redis import Redis
from rq import Queue

DEFAULT_QUEUE_NAME = "tradingagents"


def get_queue(redis_url: str, name: str = DEFAULT_QUEUE_NAME) -> Queue:
    return Queue(name, connection=Redis.from_url(redis_url))


def enqueue_fake_analysis(redis_url: str, run_id: str, db_path: str):
    queue = get_queue(redis_url)
    return queue.enqueue("tradingagents.worker.jobs.run_fake_analysis", run_id, db_path)


def enqueue_analysis(redis_url: str, run_id: str, db_path: str):
    queue = get_queue(redis_url)
    return queue.enqueue("tradingagents.worker.jobs.run_tradingagents_analysis", run_id, db_path)
