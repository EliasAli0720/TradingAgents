from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.repositories import AuditRepository
from tradingagents.api.schemas import ManualTradeRequest

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("/manual")
def manual_trade(
    payload: ManualTradeRequest,
    actor: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> dict:
    expected = f"{payload.side.upper()} {payload.ticker.upper()}"
    audit = AuditRepository(config.db_path)
    if payload.confirmation.strip().upper() != expected:
        audit.record(
            "manual_trade_failed",
            actor,
            "trade",
            "manual",
            {"ticker": payload.ticker.upper(), "side": payload.side, "reason": "bad_confirmation"},
            "rejected",
        )
        raise HTTPException(status_code=400, detail=f"Confirmation must be exactly {expected}")
    audit.record(
        "manual_trade_requested",
        actor,
        "trade",
        "manual",
        {"ticker": payload.ticker.upper(), "side": payload.side, "quantity": payload.quantity},
        "accepted",
    )
    return {"status": "queued", "ticker": payload.ticker.upper(), "side": payload.side, "quantity": payload.quantity}
