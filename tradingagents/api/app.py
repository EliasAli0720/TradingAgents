from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingagents.api.config import ApiConfig


def create_app(config: ApiConfig | None = None) -> FastAPI:
    config = config or ApiConfig.from_env()
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

    return app


app = create_app()
