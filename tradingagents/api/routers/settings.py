from __future__ import annotations

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth
from tradingagents.api.schemas import SettingsResponse
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingbot.config import TRADINGBOT_CONFIG

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(
    _: str = Depends(require_auth),
    config: ApiConfig = Depends(get_config),
) -> SettingsResponse:
    provider_env_vars = {env_var for env_var in PROVIDER_API_KEY_ENV.values() if env_var}
    env_vars = sorted(provider_env_vars | {"ALPACA_API_KEY", "ALPACA_API_SECRET"})
    provider_keys = config.provider_key_status(env_vars)
    return SettingsResponse(
        auth_enabled=config.auth_enabled,
        broker=TRADINGBOT_CONFIG.get("broker", "mock"),
        paper_trading=bool(TRADINGBOT_CONFIG.get("paper_trading", True)),
        db_path=config.db_path,
        results_dir=config.results_dir,
        provider_keys=provider_keys,
        watchlist=[ticker for ticker in TRADINGBOT_CONFIG.get("watchlist", []) if ticker],
        risk_limits={
            "max_single_position_pct": float(TRADINGBOT_CONFIG.get("max_single_position_pct", 0.10)),
            "max_total_exposure_pct": float(TRADINGBOT_CONFIG.get("max_total_exposure_pct", 0.80)),
            "daily_loss_limit_pct": float(TRADINGBOT_CONFIG.get("daily_loss_limit_pct", -0.02)),
            "min_cash_reserve": float(TRADINGBOT_CONFIG.get("min_cash_reserve", 1000.0)),
        },
        scheduler={
            "timezone": str(TRADINGBOT_CONFIG.get("timezone", "America/New_York")),
            "pre_market_time": str(TRADINGBOT_CONFIG.get("pre_market_time", "08:00")),
            "order_submission_time": str(TRADINGBOT_CONFIG.get("order_submission_time", "09:35")),
            "post_market_time": str(TRADINGBOT_CONFIG.get("post_market_time", "16:30")),
        },
    )
