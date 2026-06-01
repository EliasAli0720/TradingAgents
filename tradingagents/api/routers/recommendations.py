from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingagents.api.capacity import CapacityConfig, capacity_snapshot
from tradingagents.api.config import get_api_settings
from tradingagents.api.crypto import decrypt_secret
from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.models import User
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.recommendation_service import (
    PROMPT_VERSION,
    RecommendationGenerator,
)
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.schemas import (
    AnalyzeRecommendationCreatedResponse,
    AnalyzeRecommendationFailedResponse,
    AnalyzeRecommendationsRequest,
    AnalyzeRecommendationsResponse,
    GenerateRecommendationsRequest,
    RecommendationBatchResponse,
    RecommendationBatchSummaryResponse,
    RecommendationItemResponse,
    WatchlistRequest,
    WatchlistResponse,
)
from tradingagents.llm_clients import create_llm_client


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _item_response(item, run_status: str | None = None) -> RecommendationItemResponse:
    return RecommendationItemResponse(
        item_id=item.item_id,
        ticker=item.ticker,
        source=item.source,
        priority=item.priority,
        reason=item.reason,
        risk=item.risk,
        status=item.status,
        run_id=item.run_id,
        run_status=run_status,
        error=item.error,
    )


def _batch_response(
    repo: RecommendationRepository,
    user_id: str,
    batch,
) -> RecommendationBatchResponse:
    items = repo.list_items(user_id, batch.batch_id)
    # Reflect the linked runs' live status (and flip terminally failed ones so
    # they stop showing as stuck / become retryable). Lazy reconciliation on
    # read keeps the recommendation feature decoupled from the worker.
    live = repo.reconcile_run_statuses(items)
    return RecommendationBatchResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        created_at=batch.created_at,
        items=[_item_response(item, live.get(item.item_id)) for item in items],
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
    # An empty watchlist is allowed: the model then recommends across the broad
    # market (model_expansion) instead of being constrained to a pool.
    tickers = list(watchlist.tickers) if watchlist and watchlist.tickers else []

    generator = build_recommendation_generator(settings)
    candidates = generator.generate(
        watchlist=tickers,
        recent_context=repo.recent_analysis_context(user.user_id),
        today=date.today(),
        language=_request.language,
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
        watchlist_snapshot=tickers,
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
    response = _batch_response(repo, user.user_id, batch)
    session.commit()  # persist any status reconciliation done while reading
    return response


@router.post("/batches/{batch_id}/analyze", response_model=AnalyzeRecommendationsResponse)
def analyze_recommendations(
    batch_id: str,
    request: AnalyzeRecommendationsRequest,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AnalyzeRecommendationsResponse:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="role required")

    settings = UserModelSettingsRepository(session).snapshot(user.user_id)
    if settings is None:
        raise HTTPException(status_code=409, detail="model settings not configured")

    repo = RecommendationRepository(session)
    batch = repo.get_batch(user.user_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="recommendation batch not found")

    api_settings = get_api_settings()
    run_repo = AnalysisRunRepository(session, user_id=user.user_id)
    items = {
        item.item_id: item
        for item in repo.get_items_by_ids(user.user_id, batch_id, request.item_ids)
    }
    # Flip any item whose prior run already failed/cancelled to analysis_failed
    # so it passes the retry gate below instead of looking "already analyzed".
    repo.reconcile_run_statuses(list(items.values()))
    created: list[AnalyzeRecommendationCreatedResponse] = []
    failed: list[AnalyzeRecommendationFailedResponse] = []

    for item_id in request.item_ids:
        item = items.get(item_id)
        if item is None:
            failed.append(
                AnalyzeRecommendationFailedResponse(
                    item_id=item_id,
                    detail="recommendation item not found",
                )
            )
            continue
        # "recommended" = never analyzed; "analysis_failed" = a prior run failed
        # and may be retried. Anything else (queued/running/ignored) is skipped.
        if item.status not in ("recommended", "analysis_failed"):
            failed.append(
                AnalyzeRecommendationFailedResponse(
                    item_id=item.item_id,
                    ticker=item.ticker,
                    detail="already analyzed",
                )
            )
            continue

        capacity = capacity_snapshot(
            session,
            user.user_id,
            CapacityConfig(
                system_running=api_settings.max_running_system,
                user_running=api_settings.max_running_per_user,
                user_backlog=api_settings.max_queued_per_user,
            ),
        )
        if not capacity.can_create:
            detail = "too many queued analysis runs"
            repo.mark_analysis_failed(item, detail)
            failed.append(
                AnalyzeRecommendationFailedResponse(
                    item_id=item.item_id,
                    ticker=item.ticker,
                    detail=detail,
                )
            )
            continue

        run = run_repo.create_run(
            ticker=item.ticker,
            trade_date=date.today(),
            asset_type="stock",
            analysts=["market", "social", "news", "fundamentals"],
            user_id=user.user_id,
            llm_config=settings,
        )
        repo.mark_analysis_queued(item, run.run_id)
        created.append(
            AnalyzeRecommendationCreatedResponse(
                item_id=item.item_id,
                ticker=item.ticker,
                run_id=run.run_id,
            )
        )

    session.commit()
    return AnalyzeRecommendationsResponse(created=created, failed=failed)
