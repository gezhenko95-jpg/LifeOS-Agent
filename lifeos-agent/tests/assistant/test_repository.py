"""
AssistantRepository — против настоящей SQLite.
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant.repository import AssistantRepository
from app.db.base import Base


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def test_get_or_create_creates_default_row(session):
    repo = AssistantRepository(session)

    settings = await repo.get_or_create(1)

    assert settings.telegram_user_id == 1
    assert settings.persona == "butler"


async def test_get_or_create_returns_existing_row(session):
    repo = AssistantRepository(session)
    first = await repo.get_or_create(1)
    first.persona = "trainer"
    await repo.save(first)

    second = await repo.get_or_create(1)

    assert second.id == first.id
    assert second.persona == "trainer"


async def test_get_or_create_is_per_user(session):
    repo = AssistantRepository(session)
    first = await repo.get_or_create(1)

    second = await repo.get_or_create(2)

    assert second.telegram_user_id == 2
    assert second.id != first.id
