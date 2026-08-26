"""
ConversationHistoryRepository/Service — против настоящей SQLite
(specs/027-butler-personas-phase2.md, п.1).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.conversation.history import (
    ROLE_BOT,
    ROLE_USER,
    ConversationHistoryRepository,
    ConversationHistoryService,
)
from app.conversation.models import ConversationTurn
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


async def test_record_turn_persists_role_and_content(session):
    service = ConversationHistoryService(ConversationHistoryRepository(session))

    await service.record_turn(1, ROLE_USER, "привет")

    repo = ConversationHistoryRepository(session)
    turns = await repo.list_recent(1)
    assert len(turns) == 1
    assert turns[0].role == ROLE_USER
    assert turns[0].content == "привет"


async def test_record_exchange_writes_both_sides_in_order(session):
    service = ConversationHistoryService(ConversationHistoryRepository(session))

    await service.record_exchange(1, "как дела?", "Всё хорошо.")

    repo = ConversationHistoryRepository(session)
    turns = await repo.list_recent(1)
    assert [t.role for t in turns] == [ROLE_USER, ROLE_BOT]
    assert [t.content for t in turns] == ["как дела?", "Всё хорошо."]


async def test_list_recent_returns_chronological_order_within_window(session):
    repo = ConversationHistoryRepository(session)
    for i in range(5):
        await repo.add(
            ConversationTurn(telegram_user_id=1, role=ROLE_USER, content=str(i))
        )

    turns = await repo.list_recent(1, limit=3)

    # Последние 3 из 5 (2,3,4), но в хронологическом порядке — не
    # развёрнутые вверх ногами.
    assert [t.content for t in turns] == ["2", "3", "4"]


async def test_list_recent_scoped_to_user(session):
    repo = ConversationHistoryRepository(session)
    await repo.add(ConversationTurn(telegram_user_id=1, role=ROLE_USER, content="a"))
    await repo.add(ConversationTurn(telegram_user_id=2, role=ROLE_USER, content="b"))

    turns = await repo.list_recent(1)

    assert [t.content for t in turns] == ["a"]


async def test_format_recent_returns_empty_string_when_no_history(session):
    service = ConversationHistoryService(ConversationHistoryRepository(session))

    assert await service.format_recent(1) == ""


async def test_format_recent_labels_speakers(session):
    service = ConversationHistoryService(ConversationHistoryRepository(session))
    await service.record_exchange(1, "как дела?", "Всё хорошо.")

    formatted = await service.format_recent(1)

    assert formatted == "Пользователь: как дела?\nТы: Всё хорошо."
