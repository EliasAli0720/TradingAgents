from __future__ import annotations

import os

from fastapi import HTTPException

from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.api.schemas import CreateRunRequest
from tradingagents.llm_clients.api_key_env import get_api_key_env


class RunService:
    def __init__(self, db_path: str):
        self.runs = RunRepository(db_path)
        self.events = RunEventRepository(db_path)

    def create_run(self, request: CreateRunRequest) -> dict:
        env_var = get_api_key_env(request.llm_provider)
        if env_var and not os.getenv(env_var):
            raise HTTPException(
                status_code=400,
                detail=f"{env_var} is required for provider {request.llm_provider}",
            )
        run = self.runs.create_run(
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            asset_type=request.asset_type,
            config=request.model_dump(),
        )
        self.events.append(run["id"], "queued", {"ticker": run["ticker"]})
        return run

    def list_runs(self) -> list[dict]:
        return self.runs.list_runs()

    def get_run(self, run_id: str) -> dict:
        return self.runs.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict:
        run = self.runs.update_status(run_id, "cancel_requested")
        self.events.append(run_id, "cancel_requested", {"run_id": run_id})
        return run
