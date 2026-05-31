from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingagents.api.crypto import decrypt_secret
from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.models import User
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.recommendation_service import (
    PROMPT_VERSION,
    RecommendationGenerator,
)
from tradingagents.api.schemas import (
    GenerateRecommendationsRequest,
    RecommendationBatchResponse,
    RecommendationBatchSummaryResponse,
    RecommendationItemResponse,
    WatchlistRequest,
    WatchlistResponse,
)
from tradingagents.llm_clients import create_llm_client


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _item_response(item) -> RecommendationItemResponse:
    return RecommendationItemResponse(
        item_id=item.item_id,
        ticker=item.ticker,
        source=item.source,
        priority=item.priority,
        reason=item.reason,
        risk=item.risk,
        status=item.status,
        run_id=item.run_id,
        error=item.error,
    )


def _batch_response(
    repo: RecommendationRepository,
    user_id: str,
    batch,
) -> RecommendationBatchResponse:
    return RecommendationBatchResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        created_at=batch.created_at,
        items=[
            _item_response(item)
            for item in repo.list_items(user_id, batch.batch_id)
        ],
    )


def build_recommendation_generator(settings) -> RecommendationGenerator:
    kwargs = {}
    if settings.encrypted_api_key:
        kwargs["api_key"] = decrypt_secret(settings.encrypted_api_key)
    client = create_llm_client(
        provider=settings.llm_provider,
        model=settings.quick_think_llm,
        base_url=settings.backend_url,
        **kwargs,
    )
    return RecommendationGenerator(client.get_llm())


@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> WatchlistResponse:
    watchlist = RecommendationRepository(session).get_watchlist(user.user_id)
    if watchlist is None:
        return WatchlistResponse(tickers=[], updated_at=None)
    return WatchlistResponse(
        tickers=list(watchlist.tickers or []),
        updated_at=watchlist.updated_at,
    )


@router.put("/watchlist", response_model=WatchlistResponse)
def put_watchlist(
    request: WatchlistRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> WatchlistResponse:
    repo = RecommendationRepository(session)
    try:
        watchlist = repo.upsert_watchlist(user.user_id, request.tickers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    return WatchlistResponse(
        tickers=list(watchlist.tickers or []),
        updated_at=watchlist.updated_at,
    )


@router.post("/generate", response_model=RecommendationBatchResponse)
def generate_recommendations(
    _request: GenerateRecommendationsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> RecommendationBatchResponse:
    settings = UserModelSettingsRepository(session).get(user.user_id)
    if settings is None:
        raise HTTPException(status_code=409, detail="model settings not configured")

    repo = RecommendationRepository(session)
    watchlist = repo.get_watchlist(user.user_id)
    if watchlist is None or not watchlist.tickers:
        raise HTTPException(status_code=409, detail="watchlist not configured")

    generator = build_recommendation_generator(settings)
    candidates = generator.generate(
        watchlist=list(watchlist.tickers),
        recent_context=repo.recent_analysis_context(user.user_id),
        today=date.today(),
    )
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail="model returned no valid recommendations",
        )

    model_snapshot = {
        "llm_provider": settings.llm_provider,
        "quick_think_llm": settings.quick_think_llm,
        "deep_think_llm": settings.deep_think_llm,
        "backend_url": settings.backend_url,
    }
    batch = repo.create_batch(
        user_id=user.user_id,
        watchlist_snapshot=list(watchlist.tickers),
        model_snapshot=model_snapshot,
        items=[candidate.__dict__ for candidate in candidates[:5]],
        prompt_version=PROMPT_VERSION,
    )
    session.commit()
    return _batch_response(repo, user.user_id, batch)


@router.get("/batches", response_model=list[RecommendationBatchSummaryResponse])
def list_batches(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[RecommendationBatchSummaryResponse]:
    repo = RecommendationRepository(session)
    return [
        RecommendationBatchSummaryResponse(
            batch_id=batch.batch_id,
            status=batch.status,
            created_at=batch.created_at,
            item_count=len(repo.list_items(user.user_id, batch.batch_id)),
        )
        for batch in repo.list_batches(user.user_id)
    ]


@router.get("/batches/{batch_id}", response_model=RecommendationBatchResponse)
def get_batch(
    batch_id: str,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> RecommendationBatchResponse:
    repo = RecommendationRepository(session)
    batch = repo.get_batch(user.user_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="recommendation batch not found")
    return _batch_response(repo, user.user_id, batch)
