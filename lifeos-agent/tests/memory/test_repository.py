"""
Интеграционный тест MemoryRepository.list_by_type_since (по образцу
tests/tasks/test_completed_repository.py) — нужен Personal Insights
(app/insights/service.py, specs/009-personal-insights.md).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.memory.models import MemoryEntry, MemoryType
from app.memory.repository import MemoryRepository

NOW = datetime.now(timezone.utc)
WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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
