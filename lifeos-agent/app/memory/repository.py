"""
Репозиторий для записей памяти.

Единственное место, где выполняются SQL-запросы к таблице
`memory_entries`. Никакой бизнес-логики — только чтение/запись.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.core.repository import BaseRepository, escape_like
from app.memory.models import MemoryEntry, MemoryType


class MemoryRepository(BaseRepository[MemoryEntry]):
    """Доступ к таблице `memory_entries` через AsyncSession."""

    model = MemoryEntry

    async def list_by_user(
        self,
        telegram_user_id: int,
        type: Optional[MemoryType] = None,
        include_archived: bool = False,
        limit: Optional[int] = None,
    ) -> list[MemoryEntry]:
        query = select(MemoryEntry).where(
            MemoryEntry.telegram_user_id == telegram_user_id
        )
        if type is not None:
            query = query.where(MemoryEntry.type == type.value)
        if not include_archived:
            query = query.where(MemoryEntry.archived.is_(False))
        query = query.order_by(MemoryEntry.created_at.desc())
        if limit is not None:
            # Без limit — вся таблица пользователя вытягивается в Python
            # ради нескольких строк (тот же паттерн P-2 из AUDIT.md,
            # который уже чинили для search() ниже). Добавлено ради
            # ConversationEngine._gather_chat_context
            # (specs/020-butler-personas.md): она читает контекст на
            # КАЖДОЕ разговорное сообщение, а не по запросу раз в день,
            # как остальные вызовы этого метода — без LIMIT в БД это
            # растущая со временем использования стоимость на самом
            # частом пути, который эта же фича и должна оживить.
            query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_type_since(
        self, telegram_user_id: int, type: MemoryType, since: datetime
    ) -> list[MemoryEntry]:
        """Записи заданного типа начиная с `since` — для Personal Insights
        (см. app/insights/service.py), не тянем всю историю целиком."""
        query = select(MemoryEntry).where(
            MemoryEntry.telegram_user_id == telegram_user_id,
            MemoryEntry.type == type.value,
            MemoryEntry.created_at >= since,
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def search(
        self,
        telegram_user_id: int,
        needle: str,
        type: Optional[MemoryType] = None,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Подстрока в content, регистронезависимо, в БД (ILIKE) — раньше
        MemoryService.search тянул ВСЕ записи пользователя и фильтровал
        их в Python (см. AUDIT.md, P-2): на каждое "напомни про X" из
        памяти выгружалась целиком вся история, лишь бы найти несколько
        строк. Порядок (created_at desc) как у list_by_user, чтобы
        поведение не поменялось для вызывающего кода."""
        query = select(MemoryEntry).where(
            MemoryEntry.telegram_user_id == telegram_user_id,
            MemoryEntry.content.ilike(f"%{escape_like(needle)}%", escape="\\"),
        )
        if type is not None:
            query = query.where(MemoryEntry.type == type.value)
        if not include_archived:
            query = query.where(MemoryEntry.archived.is_(False))
        query = query.order_by(MemoryEntry.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_with_embeddings(
        self, telegram_user_id: int, type: Optional[MemoryType] = None
    ) -> list[MemoryEntry]:
        """Записи пользователя, для которых уже посчитан embedding — для
        семантического поиска (см. app/memory/service.py::semantic_search,
        specs/011-semantic-memory-search.md)."""
        query = select(MemoryEntry).where(
            MemoryEntry.telegram_user_id == telegram_user_id,
            MemoryEntry.embedding.is_not(None),
            MemoryEntry.archived.is_(False),
        )
        if type is not None:
            query = query.where(MemoryEntry.type == type.value)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_missing_embeddings(self, limit: int) -> list[MemoryEntry]:
        """Через всех пользователей — проект single-user (PROJECT.md),
        как и list_due_unreminded у задач. Для фоновой доливки embedding
        (см. app/telegram/jobs.py::embed_pending_memories_job)."""
        query = (
            select(MemoryEntry)
            .where(MemoryEntry.embedding.is_(None), MemoryEntry.archived.is_(False))
            .order_by(MemoryEntry.created_at)
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
