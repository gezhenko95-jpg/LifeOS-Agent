from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.ai.client import AIServiceError
from app.memory.models import MemoryEntry, MemoryType
from app.memory.service import MemoryService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda entry: entry
    repo.save.side_effect = lambda entry: entry
    # Реальная фильтрация теперь в БД (см. app/memory/repository.py,
    # AUDIT.md P-2). Настоящая SQL-версия проверяется отдельно, против
    # SQLite: tests/memory/test_repository.py.
    repo.search.side_effect = lambda telegram_user_id, needle, type=None: [
        entry
        for entry in repo.list_by_user.return_value
        if needle.lower() in entry.content.lower()
    ]
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


async def test_semantic_search_no_entries_with_embedding_returns_empty(repository):
    repository.list_with_embeddings.return_value = []
    service = MemoryService(repository)
    ai_client = AsyncMock()

    result = await service.semantic_search(1, "отпуск", ai_client)

    assert result == []
    ai_client.embed.assert_not_called()


async def test_semantic_search_ranks_by_similarity(repository):
    close = MemoryEntry(id=1, telegram_user_id=1, type="fact", embedding=[1.0, 0.0])
    far = MemoryEntry(id=2, telegram_user_id=1, type="fact", embedding=[0.0, 1.0])
    repository.list_with_embeddings.return_value = [far, close]
    service = MemoryService(repository)
    ai_client = AsyncMock()
    ai_client.embed.return_value = [1.0, 0.0]

    result = await service.semantic_search(1, "отпуск", ai_client)

    assert [entry.id for entry in result] == [1, 2]


async def test_semantic_search_ai_error_returns_empty(repository):
    repository.list_with_embeddings.return_value = [
        MemoryEntry(id=1, telegram_user_id=1, type="fact", embedding=[1.0])
    ]
    service = MemoryService(repository)
    ai_client = AsyncMock()
    ai_client.embed.side_effect = AIServiceError("boom")

    result = await service.semantic_search(1, "отпуск", ai_client)

    assert result == []


async def test_backfill_embeddings_saves_computed_vectors(repository):
    entry = MemoryEntry(id=1, telegram_user_id=1, type="fact", content="X")
    repository.list_missing_embeddings.return_value = [entry]
    service = MemoryService(repository)
    ai_client = AsyncMock()
    ai_client.embed.return_value = [0.1, 0.2]

    count = await service.backfill_embeddings(ai_client)

    assert count == 1
    assert entry.embedding == [0.1, 0.2]
    repository.save.assert_awaited_once_with(entry)


async def test_backfill_embeddings_skips_failed_entry_without_stopping_batch(
    repository,
):
    ok_entry = MemoryEntry(id=1, telegram_user_id=1, type="fact", content="A")
    failing_entry = MemoryEntry(id=2, telegram_user_id=1, type="fact", content="B")
    repository.list_missing_embeddings.return_value = [failing_entry, ok_entry]
    service = MemoryService(repository)
    ai_client = AsyncMock()
    ai_client.embed.side_effect = [AIServiceError("boom"), [0.1]]

    count = await service.backfill_embeddings(ai_client)

    assert count == 1
    assert ok_entry.embedding == [0.1]
    repository.save.assert_awaited_once_with(ok_entry)


async def test_backfill_embeddings_nothing_to_do_returns_zero(repository):
    repository.list_missing_embeddings.return_value = []
    service = MemoryService(repository)
    ai_client = AsyncMock()

    count = await service.backfill_embeddings(ai_client)

    assert count == 0
    repository.save.assert_not_awaited()


async def test_list_journal_entries_since_delegates_to_repository(repository):
    entry = MemoryEntry(telegram_user_id=1, type=MemoryType.JOURNAL.value, content="X")
    repository.list_by_type_since.return_value = [entry]
    service = MemoryService(repository)
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)

    entries = await service.list_journal_entries_since(1, since)

    assert entries == [entry]
    repository.list_by_type_since.assert_awaited_once_with(1, MemoryType.JOURNAL, since)


def _stored_entry(repository, content: str = "Люблю кофе") -> MemoryEntry:
    """Положить в мок-репозиторий готовую запись с уже посчитанным
    вектором — get_by_id по умолчанию возвращает AsyncMock, у которого
    любое сравнение content даёт "не равно"."""
    entry = MemoryEntry(
        id=1, telegram_user_id=1, type="fact", content=content, source="manual"
    )
    entry.embedding = [0.1, 0.2, 0.3]
    repository.get_by_id.return_value = entry
    return entry


async def test_editing_content_resets_embedding(repository):
    """Старый вектор описывает старый текст: без сброса семантический
    поиск вечно находил бы запись по её прежнему смыслу (AUDIT.md, B-5)."""
    entry = _stored_entry(repository)

    updated = await MemoryService(repository).update(entry.id, content="Перешёл на чай")

    assert updated.content == "Перешёл на чай"
    assert updated.embedding is None


async def test_editing_only_archived_keeps_embedding(repository):
    """Архивация не меняет смысл текста — пересчитывать вектор незачем,
    это лишний платный вызов к AI."""
    entry = _stored_entry(repository)

    updated = await MemoryService(repository).update(entry.id, archived=True)

    assert updated.archived is True
    assert updated.embedding == [0.1, 0.2, 0.3]


async def test_saving_identical_content_keeps_embedding(repository):
    """Текст не изменился — вектор всё ещё верен."""
    entry = _stored_entry(repository)

    updated = await MemoryService(repository).update(entry.id, content="Люблю кофе")

    assert updated.embedding == [0.1, 0.2, 0.3]
