"""
Репозиторий для записей настроения.

Единственное место, где выполняются SQL-запросы к таблице
`mood_entries`.
"""

from datetime import datetime

from sqlalchemy import desc, select

from app.core.repository import BaseRepository
from app.mood.models import MoodEntry


class MoodRepository(BaseRepository[MoodEntry]):
    model = MoodEntry

    async def list_recent(
        self, telegram_user_id: int, limit: int = 20
    ) -> list[MoodEntry]:
        """Новые сверху — для истории в боте и на /ui."""
        query = (
            select(MoodEntry)
            .where(MoodEntry.telegram_user_id == telegram_user_id)
            .order_by(desc(MoodEntry.logged_at))
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_since(
        self, telegram_user_id: int, since: datetime
    ) -> list[MoodEntry]:
        """Все записи с since — для графика в еженедельном дайджесте
        (app/scheduler/charts.py)."""
        query = (
            select(MoodEntry)
            .where(
                MoodEntry.telegram_user_id == telegram_user_id,
                MoodEntry.logged_at >= since,
            )
            .order_by(MoodEntry.logged_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
