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
        tags: Optional[str] = None,
        nudge_after_days: Optional[int] = None,
    ) -> Contact:
        name = name.strip()
        if not name:
            raise ValueError("Имя не может быть пустым")

        _validate_birthday(birthday_month, birthday_day)
        _validate_nudge_after_days(nudge_after_days)

        contact = Contact(
            telegram_user_id=telegram_user_id,
            name=name,
            birthday_month=birthday_month,
            birthday_day=birthday_day,
            notes=(notes or "").strip() or None,
            tags=(tags or "").strip() or None,
            nudge_after_days=nudge_after_days,
        )
        return await self._repository.add(contact)

    async def update_contact(
        self,
        telegram_user_id: int,
        contact_id: int,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[str] = None,
        nudge_after_days: Optional[int] = None,
        clear_nudge_after_days: bool = False,
    ) -> Optional[Contact]:
        """Раньше единственным способом изменить контакт было удалить и
        создать заново — заметка/теги/частота нэджа были только полями
        add_contact, без пути обновления (см. specs/022-tasks-v2.md —
        та же дыра в изначальной специке личного CRM, найдена по ходу
        добавления довесков к задачам).

        notes/tags — пустая строка стирает (как description у задачи),
        None — не трогать. nudge_after_days отдельным clear-флагом (как
        clear_reminder у привычек) — 0 отличим от "не трогать", но
        сброс к глобальному дефолту (None) без такого флага был бы
        неотличим от "не менял"."""
        if nudge_after_days is not None:
            _validate_nudge_after_days(nudge_after_days)

        contact = owned_or_none(
            await self._repository.get_by_id(contact_id), telegram_user_id
        )
        if contact is None:
            return None

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Имя не может быть пустым")
            contact.name = name
        if notes is not None:
            contact.notes = notes.strip() or None
        if tags is not None:
            contact.tags = tags.strip() or None
        if clear_nudge_after_days:
            contact.nudge_after_days = None
        elif nudge_after_days is not None:
            contact.nudge_after_days = nudge_after_days

        return await self._repository.save(contact)

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


def _validate_nudge_after_days(days: Optional[int]) -> None:
    if days is not None and days < 1:
        raise ValueError("Частота нэджа — минимум 1 день")
