"""
REST API для трекера настроения (specs/019-mood-tracker.md).

Эндпоинты не содержат бизнес-логики — только вызывают MoodService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_mood_service
from app.db.session import get_session
from app.mood.schemas import MoodEntryCreate, MoodEntryRead
from app.mood.service import MoodService

router = APIRouter(prefix="/mood", tags=["mood"])


def get_mood_service(session: AsyncSession = Depends(get_session)) -> MoodService:
    return build_mood_service(session)


@router.post(
    "/entries", response_model=MoodEntryRead, status_code=status.HTTP_201_CREATED
)
async def create_entry(
    payload: MoodEntryCreate,
    service: MoodService = Depends(get_mood_service),
) -> MoodEntryRead:
    try:
        entry = await service.log_mood(
            telegram_user_id=payload.telegram_user_id,
            score=payload.score,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return MoodEntryRead.model_validate(entry)


@router.get("/entries", response_model=list[MoodEntryRead])
async def list_entries(
    telegram_user_id: int,
    limit: int = 20,
    service: MoodService = Depends(get_mood_service),
) -> list[MoodEntryRead]:
    entries = await service.list_recent(telegram_user_id, limit)
    return [MoodEntryRead.model_validate(e) for e in entries]


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: int,
    telegram_user_id: int,
    service: MoodService = Depends(get_mood_service),
) -> None:
    entry = await service.delete_entry(telegram_user_id, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        )
