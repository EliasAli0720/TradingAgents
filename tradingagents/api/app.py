from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingagents.api.config import ApiConfig
from tradingagents.api.db import init_api_schema
from tradingagents.api.routers import approvals, auth, portfolio, reports, risk, runs, settings, trades


def create_app(config: ApiConfig | None = None) -> FastAPI:
    config = config or ApiConfig.from_env()
    init_api_schema(config.db_path)
    app = FastAPI(title="TradingAgents API")
    app.state.api_config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(runs.router)
    app.include_router(approvals.router)
    app.include_router(trades.router)
    app.include_router(portfolio.router)
    app.include_router(reports.router)
    app.include_router(risk.router)
    return app


app = create_app()
