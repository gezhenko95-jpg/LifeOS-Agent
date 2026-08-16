"""
Интеграционный тест DigestRepository на SQLite in-memory (по образцу
tests/watchlist/test_repository.py), включая каскадное удаление каналов
вместе с дайджестом (по образцу tests/habits/test_delete_cascade.py).
"""

import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.digest.models import Digest, DigestChannel
from app.digest.repository import DigestRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session

    await engine.dispose()


async def _add_digest(
    session, telegram_user_id=1, name="ESG", frequency=None
) -> Digest:
    repository = DigestRepository(session)
    return await repository.add(
        Digest(telegram_user_id=telegram_user_id, name=name, auto_frequency=frequency)
    )


async def test_get_by_name(session):
    await _add_digest(session, name="ESG")

    repository = DigestRepository(session)
    found = await repository.get_by_name(1, "ESG")

    assert found is not None
    assert found.auto_frequency is None


async def test_get_by_name_is_per_user(session):
    await _add_digest(session, telegram_user_id=1, name="ESG")

    repository = DigestRepository(session)

    assert await repository.get_by_name(2, "ESG") is None


async def test_list_by_user(session):
    await _add_digest(session, telegram_user_id=1, name="ESG")
    await _add_digest(session, telegram_user_id=1, name="AI")
    await _add_digest(session, telegram_user_id=2, name="Другое")

    repository = DigestRepository(session)
    digests = await repository.list_by_user(1)

    assert sorted(digest.name for digest in digests) == ["AI", "ESG"]


async def test_add_and_list_channels(session):
    digest = await _add_digest(session)
    repository = DigestRepository(session)

    await repository.add_channel(digest.id, "telegram")
    await repository.add_channel(digest.id, "durov")

    channels = await repository.list_channels(digest.id)
    assert [channel.channel_username for channel in channels] == ["telegram", "durov"]
    assert channels[0].last_seen_post_id is None


async def test_get_channel(session):
    digest = await _add_digest(session)
    repository = DigestRepository(session)
    await repository.add_channel(digest.id, "telegram")

    assert await repository.get_channel(digest.id, "telegram") is not None
    assert await repository.get_channel(digest.id, "unknown") is None


async def test_update_last_seen_post_id(session):
    digest = await _add_digest(session)
    repository = DigestRepository(session)
    channel = await repository.add_channel(digest.id, "telegram")

    await repository.update_last_seen_post_id(channel, 455)

    refreshed = await repository.get_channel(digest.id, "telegram")
    assert refreshed.last_seen_post_id == 455


async def test_remove_channel(session):
    digest = await _add_digest(session)
    repository = DigestRepository(session)
    channel = await repository.add_channel(digest.id, "telegram")

    await repository.remove_channel(channel)

    assert await repository.list_channels(digest.id) == []


async def test_deleting_digest_cascades_to_channels(session):
    digest = await _add_digest(session)
    repository = DigestRepository(session)
    await repository.add_channel(digest.id, "telegram")

    await repository.delete(digest)

    remaining = await session.execute(
        select(DigestChannel).where(DigestChannel.digest_id == digest.id)
    )
    assert remaining.scalars().all() == []
