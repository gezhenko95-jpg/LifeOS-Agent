"""
Интеграционный тест PendingPromptRepository на SQLite in-memory (по
образцу tests/tasks/test_reminders_repository.py).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.proactive.repository import PendingPromptRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def test_get_for_user_returns_none_when_nothing_open(session):
    repository = PendingPromptRepository(session)

    result = await repository.get_for_user(1)

    assert result is None


async def test_upsert_creates_new_row(session):
    repository = PendingPromptRepository(session)

    prompt = await repository.upsert(1, "goal", "Какая у тебя цель?")

    assert prompt.telegram_user_id == 1
    assert prompt.category == "goal"
    assert prompt.question_text == "Какая у тебя цель?"

    stored = await repository.get_for_user(1)
    assert stored is not None
    assert stored.id == prompt.id


async def test_upsert_overwrites_previous_unanswered(session):
    repository = PendingPromptRepository(session)
    first = await repository.upsert(1, "goal", "Первый вопрос")

    second = await repository.upsert(1, "habit", "Второй вопрос")

    assert second.id == first.id  # та же строка, не новая
    stored = await repository.get_for_user(1)
    assert stored.category == "habit"
    assert stored.question_text == "Второй вопрос"


async def test_upsert_is_isolated_per_user(session):
    repository = PendingPromptRepository(session)
    await repository.upsert(1, "goal", "Вопрос для юзера 1")
    await repository.upsert(2, "habit", "Вопрос для юзера 2")

    first = await repository.get_for_user(1)
    second = await repository.get_for_user(2)

    assert first.category == "goal"
    assert second.category == "habit"


async def test_clear_for_user_removes_row(session):
    repository = PendingPromptRepository(session)
    await repository.upsert(1, "goal", "Вопрос")

    await repository.clear_for_user(1)

    assert await repository.get_for_user(1) is None


async def test_clear_for_user_when_nothing_open_is_noop(session):
    repository = PendingPromptRepository(session)

    await repository.clear_for_user(1)  # не должно бросить исключение

    assert await repository.get_for_user(1) is None
