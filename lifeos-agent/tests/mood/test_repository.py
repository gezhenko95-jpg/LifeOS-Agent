"""
MoodRepository — против настоящей SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.mood.models import MoodEntry
from app.mood.repository import MoodRepository

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add(session, **kwargs) -> MoodEntry:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("score", 3)
    kwargs.setdefault("logged_at", NOW)
    entry = MoodEntry(**kwargs)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_list_recent_orders_newest_first(session):
    repo = MoodRepository(session)
    older = await _add(session, logged_at=NOW - timedelta(days=2))
    newer = await _add(session, logged_at=NOW - timedelta(hours=1))

    result = await repo.list_recent(1)

    assert result == [newer, older]


async def test_list_recent_filters_by_user(session):
    repo = MoodRepository(session)
    await _add(session, telegram_user_id=2)
    mine = await _add(session, telegram_user_id=1)

    result = await repo.list_recent(1)

    assert result == [mine]


async def test_list_recent_respects_limit(session):
    repo = MoodRepository(session)
    for i in range(5):
        await _add(session, logged_at=NOW - timedelta(hours=i))

    result = await repo.list_recent(1, limit=3)

    assert len(result) == 3


async def test_list_since_filters_by_date(session):
    repo = MoodRepository(session)
    await _add(session, logged_at=NOW - timedelta(days=40))
    recent = await _add(session, logged_at=NOW - timedelta(days=1))

    result = await repo.list_since(1, NOW - timedelta(days=10))

    assert result == [recent]


async def test_list_since_orders_oldest_first(session):
    repo = MoodRepository(session)
    later = await _add(session, logged_at=NOW - timedelta(hours=1))
    earlier = await _add(session, logged_at=NOW - timedelta(hours=5))

    result = await repo.list_since(1, NOW - timedelta(days=1))

    assert result == [earlier, later]
