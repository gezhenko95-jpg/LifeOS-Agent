"""
Интеграционный тест WatchlistRepository на SQLite in-memory (по образцу
tests/tasks/test_completed_repository.py).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.watchlist.models import WatchlistItem
from app.watchlist.repository import WatchlistRepository


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
    session, telegram_user_id=1, status="to_watch", **kwargs
) -> WatchlistItem:
    item = WatchlistItem(
        telegram_user_id=telegram_user_id,
        title=kwargs.pop("title", "Дюна"),
        media_type=kwargs.pop("media_type", "movie"),
        status=status,
        **kwargs,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def test_add_and_get_by_id(session):
    repository = WatchlistRepository(session)
    item = await repository.add(WatchlistItem(telegram_user_id=1, title="Дюна"))

    fetched = await repository.get_by_id(item.id)

    assert fetched is not None
    assert fetched.title == "Дюна"
    assert fetched.status == "to_watch"  # default


async def test_get_by_id_not_found(session):
    repository = WatchlistRepository(session)

    assert await repository.get_by_id(999) is None


async def test_list_by_user_filters_by_status(session):
    to_watch = await _add(session, status="to_watch")
    await _add(session, status="done")

    repository = WatchlistRepository(session)
    items = await repository.list_by_user(1, status="to_watch")

    assert [item.id for item in items] == [to_watch.id]


async def test_list_by_user_isolated_per_user(session):
    await _add(session, telegram_user_id=1)
    await _add(session, telegram_user_id=2)

    repository = WatchlistRepository(session)
    items = await repository.list_by_user(1)

    assert len(items) == 1
    assert items[0].telegram_user_id == 1


async def test_save_persists_changes(session):
    item = await _add(session)
    repository = WatchlistRepository(session)
    item.status = "done"

    saved = await repository.save(item)

    assert saved.status == "done"


async def test_delete_removes_item(session):
    item = await _add(session)
    repository = WatchlistRepository(session)

    await repository.delete(item)

    assert await repository.get_by_id(item.id) is None
