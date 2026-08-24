"""
Репозиторий для контактов личного CRM.

Единственное место, где выполняются SQL-запросы к таблице `contacts`.
"""

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.crm.models import Contact, ContactComment


class ContactRepository(BaseRepository[Contact]):
    model = Contact

    async def list_by_user(self, telegram_user_id: int) -> list[Contact]:
        """Давние контакты сверху — порядок = "с кем написать в первую
        очередь" (см. build_contacts_message)."""
        query = (
            select(Contact)
            .where(Contact.telegram_user_id == telegram_user_id)
            .order_by(Contact.last_contact_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())


class ContactCommentRepository(BaseRepository[ContactComment]):
    """Доступ к таблице `contact_comments`. Отдельный класс от
    ContactRepository — разные модели (ADR-005), прямая копия
    TaskCommentRepository (app/tasks/repository.py)."""

    model = ContactComment

    async def list_by_contact(self, contact_id: int) -> list[ContactComment]:
        query = (
            select(ContactComment)
            .where(ContactComment.contact_id == contact_id)
            .order_by(ContactComment.created_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_by_contacts(self, contact_ids: list[int]) -> dict[int, int]:
        if not contact_ids:
            return {}
        query = (
            select(ContactComment.contact_id, func.count())
            .where(ContactComment.contact_id.in_(contact_ids))
            .group_by(ContactComment.contact_id)
        )
        result = await self._session.execute(query)
        return {contact_id: count for contact_id, count in result.all()}
