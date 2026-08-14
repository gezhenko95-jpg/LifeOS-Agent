"""
Репозиторий для записей Watchlist.

Единственное место, где выполняются SQL-запросы к таблице
`watchlist_items`. Никакой бизнес-логики — только чтение/запись.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.watchlist.models import WatchlistItem


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: WatchlistItem) -> WatchlistItem:
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def get_by_id(self, item_id: int) -> Optional[WatchlistItem]:
        return await self._session.get(WatchlistItem, item_id)

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

    async def save(self, item: WatchlistItem) -> WatchlistItem:
        """Сохранить изменения существующей записи (update)."""
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def delete(self, item: WatchlistItem) -> None:
        await self._session.delete(item)
        await self._session.commit()
