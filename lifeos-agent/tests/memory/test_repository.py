"""
Интеграционный тест MemoryRepository.list_by_type_since (по образцу
tests/tasks/test_completed_repository.py) — нужен Personal Insights
(app/insights/service.py, specs/009-personal-insights.md).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.memory.models import MemoryEntry, MemoryType
from app.memory.repository import MemoryRepository
from tests.support import sqlite_engine

NOW = datetime.now(timezone.utc)
WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def session():
    # sqlite_engine (не create_async_engine напрямую) — MemoryRepository
    # .search использует ILIKE, а встроенный lower() у SQLite не понимает
    # кириллицу (см. tests/support.py).
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _add(
    session, telegram_user_id=1, type=MemoryType.JOURNAL, **kwargs
) -> MemoryEntry:
    entry = MemoryEntry(
        telegram_user_id=telegram_user_id,
        type=type.value,
        content="X",
        **kwargs,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_returns_only_matching_type_within_period(session):
    in_range = await _add(session, created_at=NOW - timedelta(days=1))
    await _add(session, created_at=WEEK_AGO - timedelta(days=1))  # раньше периода
    await _add(session, type=MemoryType.FACT, created_at=NOW)  # другой тип

    repository = MemoryRepository(session)
    entries = await repository.list_by_type_since(1, MemoryType.JOURNAL, WEEK_AGO)

    assert [entry.id for entry in entries] == [in_range.id]


async def test_isolated_per_user(session):
    await _add(session, telegram_user_id=1, created_at=NOW)
    await _add(session, telegram_user_id=2, created_at=NOW)

    repository = MemoryRepository(session)
    entries = await repository.list_by_type_since(1, MemoryType.JOURNAL, WEEK_AGO)

    assert len(entries) == 1
    assert entries[0].telegram_user_id == 1


async def test_empty_when_nothing_matches(session):
    await _add(session, type=MemoryType.FACT, created_at=NOW)

    repository = MemoryRepository(session)
    entries = await repository.list_by_type_since(1, MemoryType.JOURNAL, WEEK_AGO)

    assert entries == []


# --- list_with_embeddings / list_missing_embeddings ------------------


async def test_list_with_embeddings_only_returns_entries_that_have_one(session):
    with_embedding = await _add(session, created_at=NOW, embedding=[0.1, 0.2])
    await _add(session, created_at=NOW, embedding=None)

    repository = MemoryRepository(session)
    entries = await repository.list_with_embeddings(1)

    assert [entry.id for entry in entries] == [with_embedding.id]


async def test_list_with_embeddings_filters_by_type(session):
    await _add(session, type=MemoryType.JOURNAL, created_at=NOW, embedding=[0.1])
    fact = await _add(session, type=MemoryType.FACT, created_at=NOW, embedding=[0.2])

    repository = MemoryRepository(session)
    entries = await repository.list_with_embeddings(1, type=MemoryType.FACT)

    assert [entry.id for entry in entries] == [fact.id]


async def test_list_with_embeddings_excludes_archived(session):
    await _add(session, created_at=NOW, embedding=[0.1], archived=True)

    repository = MemoryRepository(session)
    entries = await repository.list_with_embeddings(1)

    assert entries == []


async def test_list_missing_embeddings_returns_entries_without_one(session):
    missing = await _add(session, created_at=NOW, embedding=None)
    await _add(session, created_at=NOW, embedding=[0.1])

    repository = MemoryRepository(session)
    entries = await repository.list_missing_embeddings(limit=10)

    assert [entry.id for entry in entries] == [missing.id]


async def test_list_missing_embeddings_respects_limit(session):
    for _ in range(5):
        await _add(session, created_at=NOW, embedding=None)

    repository = MemoryRepository(session)
    entries = await repository.list_missing_embeddings(limit=2)

    assert len(entries) == 2


# --- MemoryRepository.search: фильтр в БД, не в Python (AUDIT.md, P-2) ---


async def test_search_finds_case_insensitive_substring(session):
    entry = MemoryEntry(
        telegram_user_id=1, type="fact", content="Живу в Москве", source="manual"
    )
    session.add(entry)
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "москве")

    assert len(results) == 1


async def test_search_respects_limit(session):
    """specs/020-butler-personas.md — ConversationEngine._recall передаёт
    _MAX_RECALL_RESULTS в запрос, а не режет список в Python после
    фетча всех совпадений ILIKE (тот же приём, что у list_by_user)."""
    session.add_all(
        [
            MemoryEntry(
                telegram_user_id=1,
                type="fact",
                content=f"Работа {i}",
                source="manual",
            )
            for i in range(5)
        ]
    )
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "Работа", limit=2)

    assert len(results) == 2


async def test_search_percent_is_treated_literally(session):
    session.add_all(
        [
            MemoryEntry(
                telegram_user_id=1,
                type="fact",
                content="Скидка 5% на всё",
                source="manual",
            ),
            MemoryEntry(
                telegram_user_id=1,
                type="fact",
                content="Другая запись",
                source="manual",
            ),
        ]
    )
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "5%")

    assert len(results) == 1
    assert "5%" in results[0].content


async def test_search_excludes_archived_by_default(session):
    session.add(
        MemoryEntry(
            telegram_user_id=1,
            type="fact",
            content="Живу в Москве",
            source="manual",
            archived=True,
        )
    )
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "москве")

    assert results == []


async def test_search_respects_type_filter(session):
    session.add_all(
        [
            MemoryEntry(
                telegram_user_id=1,
                type="fact",
                content="Живу в Москве",
                source="manual",
            ),
            MemoryEntry(
                telegram_user_id=1,
                type="journal",
                content="Гулял по Москве",
                source="manual",
            ),
        ]
    )
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "москве", type=MemoryType.FACT)

    assert len(results) == 1
    assert results[0].type == "fact"


async def test_search_ignores_other_users_entries(session):
    session.add(
        MemoryEntry(
            telegram_user_id=2, type="fact", content="Живу в Москве", source="manual"
        )
    )
    await session.commit()
    repo = MemoryRepository(session)

    results = await repo.search(1, "москве")

    assert results == []


async def test_list_by_user_respects_limit(session):
    """specs/020-butler-personas.md — ConversationEngine._gather_chat_context
    вызывает это на каждое разговорное сообщение, LIMIT должен уходить
    в запрос, а не резать список в Python после фетча всей таблицы."""
    for i in range(5):
        await _add(session, created_at=NOW - timedelta(minutes=i))

    repository = MemoryRepository(session)
    entries = await repository.list_by_user(1, limit=3)

    assert len(entries) == 3


async def test_list_by_user_without_limit_returns_everything(session):
    for i in range(5):
        await _add(session, created_at=NOW - timedelta(minutes=i))

    repository = MemoryRepository(session)
    entries = await repository.list_by_user(1)

    assert len(entries) == 5


async def test_list_by_user_limit_keeps_newest_first(session):
    older = await _add(session, created_at=NOW - timedelta(days=2))
    newer = await _add(session, created_at=NOW - timedelta(hours=1))

    repository = MemoryRepository(session)
    entries = await repository.list_by_user(1, limit=1)

    assert entries == [newer]
    assert older not in entries
