from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tradingagents.api.config import ApiConfig

bearer = HTTPBearer(auto_error=False)


def get_config(request: Request) -> ApiConfig:
    return request.app.state.api_config


def require_auth(
    config: ApiConfig = Depends(get_config),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if not config.auth_enabled:
        return "local"
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if credentials.credentials != config.api_token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return "session:token"
