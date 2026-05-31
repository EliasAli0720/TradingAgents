from __future__ import annotations

from fastapi import FastAPI

from tradingagents.api.config import get_api_settings
from tradingagents.api.db import init_db
from tradingagents.api.middleware import CsrfMiddleware
from tradingagents.api.routers import (
    admin,
    auth,
    broker,
    broker_oauth,
    capacity,
    health,
    recommendations,
    runs,
    settings,
)


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Analysis API")
    api_settings = get_api_settings()
    app.add_middleware(
        CsrfMiddleware,
        csrf_cookie_name=api_settings.csrf_cookie_name,
        session_cookie_name=api_settings.session_cookie_name,
        # Auth routes are exempt because callers do not yet hold a CSRF cookie
        # at login/registration time. All other state-changing routes require
        # the double-submit CSRF check when a session cookie is present.
        exempt_paths=("/auth/login", "/auth/register"),
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(runs.router)
    app.include_router(admin.router)
    app.include_router(capacity.router)
    app.include_router(broker.router)
    app.include_router(recommendations.router)
    app.include_router(broker_oauth.router)

    @app.on_event("startup")
    def _startup():
        init_db()

    return app


app = create_app()
