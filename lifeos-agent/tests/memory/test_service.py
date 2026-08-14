from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.memory.models import MemoryEntry, MemoryType
from app.memory.service import MemoryService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda entry: entry
    repo.save.side_effect = lambda entry: entry
    return repo


async def test_save_creates_entry(repository):
    service = MemoryService(repository)

    entry = await service.save(1, MemoryType.FACT, "Живу в Москве")

    assert entry.content == "Живу в Москве"
    assert entry.type == "fact"
    assert entry.source == "manual"
    repository.add.assert_awaited_once()


async def test_save_strips_content(repository):
    service = MemoryService(repository)

    entry = await service.save(1, MemoryType.FACT, "  Живу в Москве  ")

    assert entry.content == "Живу в Москве"


async def test_save_empty_content_raises(repository):
    service = MemoryService(repository)

    with pytest.raises(ValueError):
        await service.save(1, MemoryType.FACT, "   ")


async def test_update_content_and_archived(repository):
    entry = MemoryEntry(telegram_user_id=1, type="fact", content="old", source="manual")
    repository.get_by_id.return_value = entry
    service = MemoryService(repository)

    updated = await service.update(1, content="new", archived=True)

    assert updated is not None
    assert updated.content == "new"
    assert updated.archived is True
    assert updated.updated_at is not None


async def test_update_nonexistent_returns_none(repository):
    repository.get_by_id.return_value = None
    service = MemoryService(repository)

    result = await service.update(999, content="new")

    assert result is None


async def test_delete_existing(repository):
    entry = MemoryEntry(telegram_user_id=1, type="fact", content="old", source="manual")
    repository.get_by_id.return_value = entry
    service = MemoryService(repository)

    result = await service.delete(1)

    assert result is entry
    repository.delete.assert_awaited_once_with(entry)


async def test_delete_nonexistent_returns_none(repository):
    repository.get_by_id.return_value = None
    service = MemoryService(repository)

    result = await service.delete(999)

    assert result is None


async def test_search_is_case_insensitive_substring(repository):
    repository.list_by_user.return_value = [
        MemoryEntry(
            telegram_user_id=1, type="fact", content="Живу в Москве", source="manual"
        ),
        MemoryEntry(
            telegram_user_id=1, type="fact", content="Люблю кофе", source="manual"
        ),
    ]
    service = MemoryService(repository)

    results = await service.search(1, "москве")

    assert len(results) == 1
    assert results[0].content == "Живу в Москве"


async def test_get_context_sorted_and_limited(repository):
    now = datetime.now(timezone.utc)
    older = MemoryEntry(telegram_user_id=1, type="fact", content="A", source="manual")
    older.created_at = now - timedelta(days=2)
    older.updated_at = None
    newer = MemoryEntry(telegram_user_id=1, type="fact", content="B", source="manual")
    newer.created_at = now - timedelta(days=1)
    newer.updated_at = now
    repository.list_by_user.return_value = [older, newer]
    service = MemoryService(repository)

    context = await service.get_context(1, limit=1)

    assert len(context) == 1
    assert context[0].content == "B"


async def test_list_journal_entries_since_delegates_to_repository(repository):
    entry = MemoryEntry(telegram_user_id=1, type=MemoryType.JOURNAL.value, content="X")
    repository.list_by_type_since.return_value = [entry]
    service = MemoryService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    entries = await service.list_journal_entries_since(1, since)

    assert entries == [entry]
    repository.list_by_type_since.assert_awaited_once_with(1, MemoryType.JOURNAL, since)
