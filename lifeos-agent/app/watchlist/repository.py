"""
Репозиторий для записей Watchlist.

Единственное место, где выполняются SQL-запросы к таблице
`watchlist_items`. Никакой бизнес-логики — только чтение/запись.
"""

from typing import Optional

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.watchlist.models import WatchlistItem


class WatchlistRepository(BaseRepository[WatchlistItem]):
    model = WatchlistItem

    async def list_by_user(
        self, telegram_user_id: int, status: Optional[str] = None
    ) -> list[WatchlistItem]:
        query = select(WatchlistItem).where(
            WatchlistItem.telegram_user_id == telegram_user_id
        )
        if status is not None:
            query = query.where(WatchlistItem.status == status)
        query = query.order_by(WatchlistItem.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())
