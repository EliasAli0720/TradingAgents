from __future__ import annotations

from fastapi import FastAPI

from tradingagents.api.db import init_db
from tradingagents.api.routers import health, runs


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analysis API")
    app.include_router(health.router)
    app.include_router(runs.router)

    @app.on_event("startup")
    def _startup():
        init_db()

    return app


app = create_app()
