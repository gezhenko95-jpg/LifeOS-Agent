"""
Mood Service (specs/019-mood-tracker.md).

Вся бизнес-логика здесь. Repository — только БД, Telegram/API —
только вызывают этот сервис.
"""

from datetime import datetime
from typing import Optional

from app.core.ownership import owned_or_none
from app.mood.models import MAX_SCORE, MIN_SCORE, MoodEntry
from app.mood.repository import MoodRepository


class MoodService:
    def __init__(self, repository: MoodRepository) -> None:
        self._repository = repository

    async def log_mood(
        self, telegram_user_id: int, score: int, note: Optional[str] = None
    ) -> MoodEntry:
        if not MIN_SCORE <= score <= MAX_SCORE:
            raise ValueError(f"Оценка должна быть от {MIN_SCORE} до {MAX_SCORE}")

        entry = MoodEntry(
            telegram_user_id=telegram_user_id,
            score=score,
            note=(note or "").strip() or None,
        )
        return await self._repository.add(entry)

    async def list_recent(
        self, telegram_user_id: int, limit: int = 20
    ) -> list[MoodEntry]:
        return await self._repository.list_recent(telegram_user_id, limit)

    async def list_since(
        self, telegram_user_id: int, since: datetime
    ) -> list[MoodEntry]:
        return await self._repository.list_since(telegram_user_id, since)

    async def delete_entry(
        self, telegram_user_id: int, entry_id: int
    ) -> Optional[MoodEntry]:
        entry = owned_or_none(
            await self._repository.get_by_id(entry_id), telegram_user_id
        )
        if entry is None:
            return None
        await self._repository.delete(entry)
        return entry
