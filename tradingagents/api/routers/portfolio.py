from __future__ import annotations

import math
from dataclasses import asdict

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingbot.broker.mock import MockBroker
from tradingbot.portfolio.database import PortfolioDatabase
from tradingbot.portfolio.manager import PortfolioManager

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _manager(config: ApiConfig) -> tuple[MockBroker, PortfolioManager]:
    broker = MockBroker(starting_cash=100_000.0)
    db = PortfolioDatabase(config.db_path)
    return broker, PortfolioManager(broker, db)


def _json_safe_numbers(payload: dict) -> dict:
    safe = dict(payload)
    for key, value in safe.items():
        if isinstance(value, float) and not math.isfinite(value):
            safe[key] = 0.0
    return safe


@router.get("/account")
def account(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    broker, _ = _manager(config)
    return asdict(broker.get_account())


@router.get("/positions")
def positions(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    broker, _ = _manager(config)
    return {"positions": [asdict(position) for position in broker.get_positions()]}


@router.get("/snapshots")
def snapshots(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    db = PortfolioDatabase(config.db_path)
    return {"snapshots": [asdict(snapshot) for snapshot in db.get_snapshots()]}


@router.get("/performance")
def performance(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    _, manager = _manager(config)
    return _json_safe_numbers(asdict(manager.get_performance_metrics()))
