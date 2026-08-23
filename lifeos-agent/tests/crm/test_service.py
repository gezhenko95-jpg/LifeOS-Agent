"""
ContactService — repository замокан.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.crm.models import Contact
from app.crm.service import ContactService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda c: c
    repo.save.side_effect = lambda c: c
    return repo


def _contact(**kwargs) -> Contact:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("name", "Аня")
    kwargs.setdefault("last_contact_at", NOW)
    return Contact(**kwargs)


async def test_add_contact_strips_name(repository):
    service = ContactService(repository)

    contact = await service.add_contact(1, "  Аня  ")

    assert contact.name == "Аня"
    repository.add.assert_awaited_once()


async def test_add_contact_rejects_empty_name(repository):
    service = ContactService(repository)

    with pytest.raises(ValueError):
        await service.add_contact(1, "   ")


async def test_add_contact_with_birthday(repository):
    service = ContactService(repository)

    contact = await service.add_contact(1, "Петя", birthday_month=9, birthday_day=14)

    assert (contact.birthday_month, contact.birthday_day) == (9, 14)


async def test_add_contact_rejects_half_birthday(repository):
    service = ContactService(repository)

    with pytest.raises(ValueError):
        await service.add_contact(1, "Петя", birthday_month=9, birthday_day=None)


async def test_add_contact_rejects_impossible_date(repository):
    service = ContactService(repository)

    with pytest.raises(ValueError):
        await service.add_contact(1, "Петя", birthday_month=2, birthday_day=30)


async def test_add_contact_accepts_leap_day(repository):
    service = ContactService(repository)

    contact = await service.add_contact(1, "Петя", birthday_month=2, birthday_day=29)

    assert (contact.birthday_month, contact.birthday_day) == (2, 29)


async def test_add_contact_empty_notes_becomes_none(repository):
    service = ContactService(repository)

    contact = await service.add_contact(1, "Аня", notes="   ")

    assert contact.notes is None


async def test_mark_contacted_updates_timestamp(repository):
    contact = _contact(id=5, last_contact_at=NOW - timedelta(days=40))
    repository.get_by_id.return_value = contact
    service = ContactService(repository)

    result = await service.mark_contacted(1, 5)

    assert result is contact
    assert (datetime.now(timezone.utc) - contact.last_contact_at) < timedelta(seconds=5)
    repository.save.assert_awaited_once_with(contact)


async def test_mark_contacted_wrong_owner_returns_none(repository):
    contact = _contact(id=5, telegram_user_id=2)
    repository.get_by_id.return_value = contact
    service = ContactService(repository)

    result = await service.mark_contacted(1, 5)

    assert result is None
    repository.save.assert_not_awaited()


async def test_mark_contacted_missing_returns_none(repository):
    repository.get_by_id.return_value = None
    service = ContactService(repository)

    result = await service.mark_contacted(1, 999)

    assert result is None


async def test_delete_contact_owned(repository):
    contact = _contact(id=5)
    repository.get_by_id.return_value = contact
    service = ContactService(repository)

    result = await service.delete_contact(1, 5)

    assert result is contact
    repository.delete.assert_awaited_once_with(contact)


async def test_delete_contact_wrong_owner_returns_none(repository):
    contact = _contact(id=5, telegram_user_id=2)
    repository.get_by_id.return_value = contact
    service = ContactService(repository)

    result = await service.delete_contact(1, 5)

    assert result is None
    repository.delete.assert_not_awaited()


async def test_list_contacts_delegates_to_repository(repository):
    repository.list_by_user.return_value = [_contact()]
    service = ContactService(repository)

    result = await service.list_contacts(1)

    assert len(result) == 1
    repository.list_by_user.assert_awaited_once_with(1)
