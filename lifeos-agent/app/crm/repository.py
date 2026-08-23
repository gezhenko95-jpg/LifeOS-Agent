"""
Репозиторий для контактов личного CRM.

Единственное место, где выполняются SQL-запросы к таблице `contacts`.
"""

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.crm.models import Contact


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
