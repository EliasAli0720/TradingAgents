from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingagents.api.deps import get_current_user, get_db_session
from tradingagents.api.models import User
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.schemas import WatchlistRequest, WatchlistResponse


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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
