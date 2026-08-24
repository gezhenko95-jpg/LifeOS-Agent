"""
REST API для фокус-сессий (specs/026-focus-sessions.md).

Эндпоинты не содержат бизнес-логики — только вызывают FocusSessionService.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_focus_service
from app.db.session import get_session
from app.focus.schemas import FocusSessionCreate, FocusSessionRead, FocusStatsRead
from app.focus.service import FocusSessionService

router = APIRouter(prefix="/focus", tags=["focus"])

_WEEK = timedelta(days=7)


def get_focus_service(
    session: AsyncSession = Depends(get_session),
) -> FocusSessionService:
    return build_focus_service(session)


@router.post(
    "/sessions", response_model=FocusSessionRead, status_code=status.HTTP_201_CREATED
)
async def start_session(
    payload: FocusSessionCreate,
    service: FocusSessionService = Depends(get_focus_service),
) -> FocusSessionRead:
    try:
        session = await service.start_session(
            telegram_user_id=payload.telegram_user_id,
            work_minutes=payload.work_minutes,
            break_minutes=payload.break_minutes,
            task_id=payload.task_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return FocusSessionRead.model_validate(session)


@router.get("/sessions/active", response_model=FocusSessionRead | None)
async def get_active_session(
    telegram_user_id: int,
    service: FocusSessionService = Depends(get_focus_service),
) -> FocusSessionRead | None:
    session = await service.get_active_session(telegram_user_id)
    return FocusSessionRead.model_validate(session) if session else None


@router.post("/sessions/{session_id}/cancel", response_model=FocusSessionRead)
async def cancel_session(
    session_id: int,
    telegram_user_id: int,
    service: FocusSessionService = Depends(get_focus_service),
) -> FocusSessionRead:
    session = await service.cancel_session(telegram_user_id, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Активная сессия не найдена",
        )
    return FocusSessionRead.model_validate(session)


@router.get("/stats", response_model=FocusStatsRead)
async def get_stats(
    telegram_user_id: int,
    service: FocusSessionService = Depends(get_focus_service),
) -> FocusStatsRead:
    since = datetime.now(timezone.utc) - _WEEK
    count, minutes = await service.stats_since(telegram_user_id, since)
    return FocusStatsRead(completed_count=count, total_minutes=minutes)
