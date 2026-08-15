"""
TaskRepository.find_active_by_title — против настоящей SQLite (см.
AUDIT.md, P-2: раньше сервис тянул ВСЕ активные задачи и фильтровал
подстроку в Python).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from tests.support import sqlite_engine


@pytest_asyncio.fixture
async def session():
    # sqlite_engine (не create_async_engine напрямую) — ILIKE в
    # find_active_by_title компилируется через lower(), а встроенный
    # lower() SQLite не понимает кириллицу (см. tests/support.py).
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add(session, title, status="active", telegram_user_id=1) -> Task:
    task = Task(telegram_user_id=telegram_user_id, title=title, status=status)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_finds_case_insensitive_substring(session):
    await _add(session, "Купить Молоко")
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "молоко")

    assert len(matches) == 1


async def test_ignores_completed_tasks(session):
    """Подстрока совпадает, но задача не активна — не должна попасть в
    результат: find_active_by_title ищет именно активные."""
    await _add(session, "Купить молоко", status="completed")
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "молоко")

    assert matches == []


async def test_ignores_other_users_tasks(session):
    await _add(session, "Купить молоко", telegram_user_id=2)
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "молоко")

    assert matches == []


async def test_percent_in_query_is_treated_literally(session):
    """Раньше это был Python `in` — буквальная подстрока. ILIKE без
    экранирования интерпретировал бы % как wildcard, совпадая с чем
    угодно (см. AUDIT.md, P-2)."""
    await _add(session, "Скидка 5% на всё")
    await _add(session, "Купить что-то ещё")
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "5%")

    assert len(matches) == 1
    assert matches[0].title == "Скидка 5% на всё"


async def test_underscore_in_query_is_treated_literally(session):
    await _add(session, "файл_с_отчётом.pdf")
    await _add(session, "файлXсXотчётом.pdf")
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "файл_с")

    assert len(matches) == 1
    assert matches[0].title == "файл_с_отчётом.pdf"


async def test_no_match_returns_empty_list(session):
    await _add(session, "Купить молоко")
    repo = TaskRepository(session)

    matches = await repo.find_active_by_title(1, "единорог")

    assert matches == []
