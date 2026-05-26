from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.models import User
from tradingagents.api.schemas import ModelSettingsRequest, ModelSettingsResponse


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/model", response_model=ModelSettingsResponse)
def get_model_settings(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    settings = UserModelSettingsRepository(session).get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="model settings not configured")
    return ModelSettingsResponse(
        llm_provider=settings.llm_provider,
        deep_think_llm=settings.deep_think_llm,
        quick_think_llm=settings.quick_think_llm,
        backend_url=settings.backend_url,
    )


@router.put("/model", response_model=ModelSettingsResponse)
def put_model_settings(
    request: ModelSettingsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    settings = UserModelSettingsRepository(session).upsert(
        user_id=user.user_id,
        llm_provider=request.llm_provider,
        deep_think_llm=request.deep_think_llm,
        quick_think_llm=request.quick_think_llm,
        backend_url=request.backend_url,
    )
    session.commit()
    return ModelSettingsResponse(
        llm_provider=settings.llm_provider,
        deep_think_llm=settings.deep_think_llm,
        quick_think_llm=settings.quick_think_llm,
        backend_url=settings.backend_url,
    )
