"""
Memory Service.

Вся бизнес-логика работы с долговременной памятью находится здесь.
Repository — только БД, API/будущий AI Service — только вызывают этот сервис.
См. specs/001-memory.md.
"""

from datetime import datetime, timezone
from typing import Optional

from app.memory.models import MemoryEntry, MemoryType
from app.memory.repository import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    async def save(
        self,
        telegram_user_id: int,
        type: MemoryType,
        content: str,
        source: str = "manual",
    ) -> MemoryEntry:
        content = content.strip()
        if not content:
            raise ValueError("Содержимое записи не может быть пустым")

        entry = MemoryEntry(
            telegram_user_id=telegram_user_id,
            type=type.value,
            content=content,
            source=source,
        )
        return await self._repository.add(entry)

    async def update(
        self,
        entry_id: int,
        content: Optional[str] = None,
        archived: Optional[bool] = None,
    ) -> Optional[MemoryEntry]:
        entry = await self._repository.get_by_id(entry_id)
        if entry is None:
            return None
        if content is not None:
            entry.content = content
        if archived is not None:
            entry.archived = archived
        entry.updated_at = datetime.now(timezone.utc)
        return await self._repository.save(entry)

    async def delete(self, entry_id: int) -> Optional[MemoryEntry]:
        entry = await self._repository.get_by_id(entry_id)
        if entry is None:
            return None
        await self._repository.delete(entry)
        return entry

    async def list_entries(
        self, telegram_user_id: int, type: Optional[MemoryType] = None
    ) -> list[MemoryEntry]:
        return await self._repository.list_by_user(telegram_user_id, type=type)

    async def list_journal_entries_since(
        self, telegram_user_id: int, since: datetime
    ) -> list[MemoryEntry]:
        """Дневниковые записи начиная с `since` — для Personal Insights
        (см. app/insights/service.py)."""
        return await self._repository.list_by_type_since(
            telegram_user_id, MemoryType.JOURNAL, since
        )

    async def search(
        self,
        telegram_user_id: int,
        query: str,
        type: Optional[MemoryType] = None,
    ) -> list[MemoryEntry]:
        needle = query.strip().lower()
        entries = await self._repository.list_by_user(telegram_user_id, type=type)
        return [entry for entry in entries if needle in entry.content.lower()]

    async def get_context(
        self, telegram_user_id: int, limit: int = 10
    ) -> list[MemoryEntry]:
        """Простой вариант "релевантного контекста" — последние N записей.

        Оценка важности и семантический поиск — будущее развитие
        (см. specs/001-memory.md), сейчас достаточно последних по времени.
        """
        entries = await self._repository.list_by_user(telegram_user_id)
        # id как второй ключ сортировки — тай-брейкер, если несколько записей
        # созданы в один и тот же момент (например, зависит от точности БД).
        entries.sort(
            key=lambda entry: (entry.updated_at or entry.created_at, entry.id),
            reverse=True,
        )
        return entries[:limit]
