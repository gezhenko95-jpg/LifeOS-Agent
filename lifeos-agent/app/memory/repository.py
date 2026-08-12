"""
Репозиторий для записей памяти.

Единственное место, где выполняются SQL-запросы к таблице
`memory_entries`. Никакой бизнес-логики — только чтение/запись.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import MemoryEntry, MemoryType


class MemoryRepository:
    """Доступ к таблице `memory_entries` через AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def get_by_id(self, entry_id: int) -> Optional[MemoryEntry]:
        return await self._session.get(MemoryEntry, entry_id)

    async def list_by_user(
        self,
        telegram_user_id: int,
        type: Optional[MemoryType] = None,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        query = select(MemoryEntry).where(
            MemoryEntry.telegram_user_id == telegram_user_id
        )
        if type is not None:
            query = query.where(MemoryEntry.type == type.value)
        if not include_archived:
            query = query.where(MemoryEntry.archived.is_(False))
        query = query.order_by(MemoryEntry.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save(self, entry: MemoryEntry) -> MemoryEntry:
        """Сохранить изменения существующей записи (update)."""
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def delete(self, entry: MemoryEntry) -> None:
        await self._session.delete(entry)
        await self._session.commit()
