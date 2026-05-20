from __future__ import annotations

from fastapi import APIRouter, Depends

from tradingagents.api.deps import require_auth
from tradingbot.config import TRADINGBOT_CONFIG

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/limits")
def limits(_: str = Depends(require_auth)) -> dict:
    return {
        "max_single_position_pct": TRADINGBOT_CONFIG.get("max_single_position_pct", 0.10),
        "max_total_exposure_pct": TRADINGBOT_CONFIG.get("max_total_exposure_pct", 0.80),
        "daily_loss_limit_pct": TRADINGBOT_CONFIG.get("daily_loss_limit_pct", -0.02),
        "min_cash_reserve": TRADINGBOT_CONFIG.get("min_cash_reserve", 1000.0),
    }


@router.get("/status")
def status(_: str = Depends(require_auth)) -> dict:
    return {
        "circuit_breaker": {"active": False, "reason": None},
        "limits": limits(_),
    }
