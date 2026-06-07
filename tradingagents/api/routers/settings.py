from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from tradingagents.api.crypto import decrypt_secret
from tradingagents.api.config import get_api_settings
from tradingagents.api.deps import get_current_user, get_db_session, get_model_probe
from tradingagents.api.model_catalog_repository import LLMModelCatalogRepository
from tradingagents.api.model_probe import ModelProbeRequest
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.models import User
from tradingagents.api.url_validation import UnsafeBackendUrl, validate_backend_url
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.api.translation_catalog import (
    TRANSLATION_PROVIDERS,
    get_translation_provider,
    validate_translation_settings,
)
from tradingagents.api.translation_settings_repository import (
    UserTranslationSettingsRepository,
)
from tradingagents.api.schemas import (
    ModelOptionResponse,
    ModelOptionsResponse,
    ModelProviderOptionResponse,
    ModelSettingsRequest,
    ModelSettingsResponse,
    ModelSettingsValidationResponse,
    TranslationOptionsResponse,
    TranslationProviderOptionResponse,
    TranslationSettingsRequest,
    TranslationSettingsResponse,
    UpdatePreferencesRequest,
)


router = APIRouter(prefix="/settings", tags=["settings"])


def _safe_backend_url(value: str | None) -> str | None:
    try:
        return validate_backend_url(
            value,
            allow_private=get_api_settings().allow_private_backend_urls,
        )
    except UnsafeBackendUrl as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/preferences", status_code=status.HTTP_204_NO_CONTENT)
def update_preferences(
    request: UpdatePreferencesRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    user.language = request.language
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _response_for_settings(
    repo: UserModelSettingsRepository,
    settings,
) -> ModelSettingsResponse:
    metadata = repo.api_key_metadata(settings)
    return ModelSettingsResponse(
        llm_provider=settings.llm_provider,
        deep_think_llm=settings.deep_think_llm,
        quick_think_llm=settings.quick_think_llm,
        backend_url=settings.backend_url,
        has_api_key=bool(metadata["has_api_key"]),
        api_key_masked=metadata["api_key_masked"],
    )


def _response_for_model_options(
    repo: LLMModelCatalogRepository,
) -> ModelOptionsResponse:
    providers = []
    for provider in repo.list_provider_options():
        quick_models = [
            ModelOptionResponse(id=model.model_id, label=model.label)
            for model in repo.list_model_options(provider.provider_id, "quick")
        ]
        deep_models = [
            ModelOptionResponse(id=model.model_id, label=model.label)
            for model in repo.list_model_options(provider.provider_id, "deep")
        ]
        providers.append(
            ModelProviderOptionResponse(
                id=provider.provider_id,
                label=provider.label,
                required_env_var=provider.required_env_var,
                default_backend_url=provider.default_backend_url,
                backend_url_editable=provider.backend_url_editable,
                supports_custom_model=provider.supports_custom_model,
                quick_models=quick_models,
                deep_models=deep_models,
            )
        )
    return ModelOptionsResponse(providers=providers)


@router.get("/model/options", response_model=ModelOptionsResponse)
def get_model_options(
    session: Session = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    repo = LLMModelCatalogRepository(session)
    response = _response_for_model_options(repo)
    session.commit()
    return response


@router.get("/model", response_model=ModelSettingsResponse)
def get_model_settings(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    repo = UserModelSettingsRepository(session)
    settings = repo.get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="model settings not configured")
    return _response_for_settings(repo, settings)


@router.put("/model", response_model=ModelSettingsResponse)
def put_model_settings(
    request: ModelSettingsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    catalog = LLMModelCatalogRepository(session)
    validation_error = catalog.validate_model_settings(
        request.llm_provider,
        request.quick_think_llm,
        request.deep_think_llm,
    )
    if validation_error:
        raise HTTPException(status_code=422, detail=validation_error)

    repo = UserModelSettingsRepository(session)
    settings = repo.upsert(
        user_id=user.user_id,
        llm_provider=request.llm_provider,
        deep_think_llm=request.deep_think_llm,
        quick_think_llm=request.quick_think_llm,
        backend_url=_safe_backend_url(request.backend_url),
        api_key=request.api_key,
    )
    session.commit()
    return _response_for_settings(repo, settings)


@router.delete("/model/api-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_api_key(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    settings = UserModelSettingsRepository(session).clear_api_key(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="model settings not configured")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/model/validate",
    response_model=ModelSettingsValidationResponse,
    response_model_exclude_none=True,
)
def validate_model_settings(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    probe=Depends(get_model_probe),
):
    settings = UserModelSettingsRepository(session).get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="model settings not configured")

    required_env_var = get_api_key_env(settings.llm_provider)
    api_key_source = "none"
    api_key = None
    message = f"missing API key for provider {settings.llm_provider}"

    if settings.encrypted_api_key:
        api_key_source = "user"
        api_key = decrypt_secret(settings.encrypted_api_key)
        message = f"user API key configured for provider {settings.llm_provider}"
    elif required_env_var is None:
        api_key_source = "not_required"
        message = f"provider {settings.llm_provider} does not require an API key"
    elif os.environ.get(required_env_var):
        api_key_source = "service"
        api_key = os.environ[required_env_var]
        message = f"service API key configured in {required_env_var}"
    else:
        return ModelSettingsValidationResponse(
            valid=False,
            provider=settings.llm_provider,
            required_env_var=required_env_var,
            api_key_source=api_key_source,
            message=message,
        )

    probe_result = probe(
        ModelProbeRequest(
            provider=settings.llm_provider,
            model=settings.quick_think_llm,
            backend_url=_safe_backend_url(settings.backend_url),
            api_key=api_key,
        )
    )
    return ModelSettingsValidationResponse(
        valid=probe_result.status == "success",
        provider=settings.llm_provider,
        required_env_var=required_env_var,
        api_key_source=api_key_source,
        message=message,
        probe_status=probe_result.status,
        probe_message=probe_result.message,
    )


# ── Translation model settings ─────────────────────────────────────────────


def _response_for_translation(
    repo: UserTranslationSettingsRepository,
    settings,
) -> TranslationSettingsResponse:
    metadata = repo.api_key_metadata(settings)
    return TranslationSettingsResponse(
        llm_provider=settings.llm_provider,
        model=settings.model,
        backend_url=settings.backend_url,
        has_api_key=bool(metadata["has_api_key"]),
        api_key_masked=metadata["api_key_masked"],
    )


@router.get("/translation/options", response_model=TranslationOptionsResponse)
def get_translation_options(_user: User = Depends(get_current_user)):
    return TranslationOptionsResponse(
        providers=[
            TranslationProviderOptionResponse(
                id=opt.provider_id,
                label=opt.label,
                model_id=opt.model_id,
                model_label=opt.model_label,
                required_env_var=opt.required_env_var,
                default_backend_url=opt.default_backend_url,
                backend_url_editable=opt.backend_url_editable,
            )
            for opt in TRANSLATION_PROVIDERS
        ]
    )


@router.get("/translation", response_model=TranslationSettingsResponse)
def get_translation_settings(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    repo = UserTranslationSettingsRepository(session)
    settings = repo.get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="translation settings not configured")
    return _response_for_translation(repo, settings)


@router.put("/translation", response_model=TranslationSettingsResponse)
def put_translation_settings(
    request: TranslationSettingsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    validation_error = validate_translation_settings(request.llm_provider, request.model)
    if validation_error:
        raise HTTPException(status_code=422, detail=validation_error)

    repo = UserTranslationSettingsRepository(session)
    settings = repo.upsert(
        user_id=user.user_id,
        llm_provider=request.llm_provider,
        model=request.model,
        backend_url=_safe_backend_url(request.backend_url),
        api_key=request.api_key,
    )
    session.commit()
    return _response_for_translation(repo, settings)


@router.delete("/translation/api-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_translation_api_key(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    settings = UserTranslationSettingsRepository(session).clear_api_key(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="translation settings not configured")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/translation/validate",
    response_model=ModelSettingsValidationResponse,
    response_model_exclude_none=True,
)
def validate_translation_model(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    probe=Depends(get_model_probe),
):
    settings = UserTranslationSettingsRepository(session).get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="translation settings not configured")

    required_env_var = get_api_key_env(settings.llm_provider)
    api_key_source = "none"
    api_key = None
    message = f"missing API key for provider {settings.llm_provider}"

    if settings.encrypted_api_key:
        api_key_source = "user"
        api_key = decrypt_secret(settings.encrypted_api_key)
        message = f"user API key configured for provider {settings.llm_provider}"
    elif required_env_var is None:
        api_key_source = "not_required"
        message = f"provider {settings.llm_provider} does not require an API key"
    elif os.environ.get(required_env_var):
        api_key_source = "service"
        api_key = os.environ[required_env_var]
        message = f"service API key configured in {required_env_var}"
    else:
        return ModelSettingsValidationResponse(
            valid=False,
            provider=settings.llm_provider,
            required_env_var=required_env_var,
            api_key_source=api_key_source,
            message=message,
        )

    probe_result = probe(
        ModelProbeRequest(
            provider=settings.llm_provider,
            model=settings.model,
            backend_url=_safe_backend_url(settings.backend_url),
            api_key=api_key,
        )
    )
    return ModelSettingsValidationResponse(
        valid=probe_result.status == "success",
        provider=settings.llm_provider,
        required_env_var=required_env_var,
        api_key_source=api_key_source,
        message=message,
        probe_status=probe_result.status,
        probe_message=probe_result.message,
    )
