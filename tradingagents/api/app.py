from __future__ import annotations

from fastapi import FastAPI

from tradingagents.api.config import get_api_settings
from tradingagents.api.db import init_db
from tradingagents.api.middleware import CsrfMiddleware
from tradingagents.api.routers import health, runs


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analysis API")
    settings = get_api_settings()
    app.add_middleware(
        CsrfMiddleware,
        csrf_cookie_name=settings.csrf_cookie_name,
        # /runs is exempted here only until Task 9 wires CSRF-aware fixtures into
        # tests/api/test_runs_routes.py. Auth routes always remain exempt because
        # callers do not yet hold a CSRF cookie at login/registration time.
        exempt_paths=("/auth/login", "/auth/register", "/runs"),
    )
    app.include_router(health.router)
    app.include_router(runs.router)

    @app.on_event("startup")
    def _startup():
        init_db()

    return app


app = create_app()
