"""
PetRepository — против настоящей SQLite (по образцу
tests/rewards/test_repository.py).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.pet.repository import PetRepository

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


async def test_get_returns_none_without_pet(session):
    repo = PetRepository(session)

    assert await repo.get(1) is None


async def test_create_then_get(session):
    repo = PetRepository(session)
    created = await repo.create(1, NOW)

    fetched = await repo.get(1)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.deaths_count == 0


async def test_pets_isolated_per_user(session):
    repo = PetRepository(session)
    await repo.create(1, NOW)

    assert await repo.get(2) is None


async def test_feed_updates_last_fed_at(session):
    repo = PetRepository(session)
    pet = await repo.create(1, NOW - timedelta(hours=10))
    later = NOW

    fed = await repo.feed(pet, later)

    assert fed.last_fed_at == later.replace(tzinfo=None)


async def test_revive_resets_last_fed_at_and_increments_deaths(session):
    repo = PetRepository(session)
    pet = await repo.create(1, NOW - timedelta(hours=200))

    revived = await repo.revive(pet, NOW)

    assert revived.deaths_count == 1
    assert revived.last_fed_at == NOW.replace(tzinfo=None)


async def test_revive_twice_increments_deaths_again(session):
    repo = PetRepository(session)
    pet = await repo.create(1, NOW - timedelta(hours=200))
    await repo.revive(pet, NOW)

    revived = await repo.revive(pet, NOW)

    assert revived.deaths_count == 2


async def test_list_all_returns_every_pet(session):
    repo = PetRepository(session)
    await repo.create(1, NOW)
    await repo.create(2, NOW)

    pets = await repo.list_all()

    assert {p.telegram_user_id for p in pets} == {1, 2}


async def test_list_all_empty_without_pets(session):
    repo = PetRepository(session)

    assert await repo.list_all() == []


async def test_mark_hungry_notified_sets_timestamp(session):
    repo = PetRepository(session)
    pet = await repo.create(1, NOW - timedelta(hours=60))

    notified = await repo.mark_hungry_notified(pet, NOW)

    assert notified.hungry_notified_at == NOW.replace(tzinfo=None)
