"""
Репозиторий для финансовых транзакций.

Единственное место, где выполняются SQL-запросы к таблице
`transactions`. Фильтрация по (telegram_user_id, occurred_at) — в БД
(индекс есть, см. миграцию 018); суммирование по категориям — в Python
в сервисе (ADR-004: объём данных личных финансов на порядки меньше, чем
у задач/памяти, где P-2 из AUDIT.md был реальной проблемой).
"""

from datetime import datetime

from sqlalchemy import desc, select

from app.core.repository import BaseRepository
from app.finance.models import Transaction


class FinanceRepository(BaseRepository[Transaction]):
    """Доступ к таблице `transactions` через AsyncSession."""

    model = Transaction

    async def list_since(
        self, telegram_user_id: int, since: datetime
    ) -> list[Transaction]:
        """Все транзакции пользователя, начиная с `since` — сервис сам
        разносит их на доход/обязательное/категории (build_period_summary)."""
        query = (
            select(Transaction)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.occurred_at >= since,
            )
            .order_by(Transaction.occurred_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_recent(
        self, telegram_user_id: int, limit: int = 10
    ) -> list[Transaction]:
        """Последние `limit` транзакций пользователя, новые сверху — для
        экрана «Список» в боте и карточки на /ui (не привязано к периоду,
        в отличие от list_since)."""
        query = (
            select(Transaction)
            .where(Transaction.telegram_user_id == telegram_user_id)
            .order_by(desc(Transaction.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
