"""
Contact Service (личный CRM, specs/018-personal-crm.md).

Вся бизнес-логика здесь. Repository — только БД, Telegram/API —
только вызывают этот сервис.
"""

from datetime import date, datetime, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.crm.models import Contact
from app.crm.repository import ContactRepository

# 1904 — произвольный високосный год, только чтобы validate_birthday
# мог проверить 29 февраля тем же способом, что и остальные даты
# (см. app/conversation/date_parser.py::_safe_date — тот же приём).
_LEAP_YEAR_FOR_VALIDATION = 1904


class ContactService:
    def __init__(self, repository: ContactRepository) -> None:
        self._repository = repository

    async def add_contact(
        self,
        telegram_user_id: int,
        name: str,
        birthday_month: Optional[int] = None,
        birthday_day: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Contact:
        name = name.strip()
        if not name:
            raise ValueError("Имя не может быть пустым")

        _validate_birthday(birthday_month, birthday_day)

        contact = Contact(
            telegram_user_id=telegram_user_id,
            name=name,
            birthday_month=birthday_month,
            birthday_day=birthday_day,
            notes=(notes or "").strip() or None,
        )
        return await self._repository.add(contact)

    async def list_contacts(self, telegram_user_id: int) -> list[Contact]:
        return await self._repository.list_by_user(telegram_user_id)

    async def mark_contacted(
        self, telegram_user_id: int, contact_id: int
    ) -> Optional[Contact]:
        contact = owned_or_none(
            await self._repository.get_by_id(contact_id), telegram_user_id
        )
        if contact is None:
            return None
        contact.last_contact_at = datetime.now(timezone.utc)
        return await self._repository.save(contact)

    async def delete_contact(
        self, telegram_user_id: int, contact_id: int
    ) -> Optional[Contact]:
        contact = owned_or_none(
            await self._repository.get_by_id(contact_id), telegram_user_id
        )
        if contact is None:
            return None
        await self._repository.delete(contact)
        return contact


def _validate_birthday(month: Optional[int], day: Optional[int]) -> None:
    """Оба поля вместе или оба None — половинчатая дата (только месяц
    или только день) бесполезна для нэджей и почти наверняка ошибка
    ввода."""
    if month is None and day is None:
        return
    if month is None or day is None:
        raise ValueError("Дата рождения — месяц и день вместе, либо ничего")
    try:
        date(_LEAP_YEAR_FOR_VALIDATION, month, day)
    except ValueError as exc:
        raise ValueError("Такой даты не существует") from exc
