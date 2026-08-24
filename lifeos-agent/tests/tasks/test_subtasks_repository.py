"""
TaskRepository.list_subtasks / count_subtasks_by_parents / top_level_only —
против настоящей SQLite (см. specs/022-tasks-v2.md, тот же приём, что
у find_active_by_title — AUDIT.md P-2).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from tests.support import sqlite_engine


@pytest_asyncio.fixture
async def session():
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add(session, title, telegram_user_id=1, parent_id=None) -> Task:
    task = Task(
        telegram_user_id=telegram_user_id,
        title=title,
        status="active",
        parent_id=parent_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_list_subtasks_returns_only_children_of_parent(session):
    repo = TaskRepository(session)
    parent = await _add(session, "Эпик")
    child1 = await _add(session, "Подзадача 1", parent_id=parent.id)
    child2 = await _add(session, "Подзадача 2", parent_id=parent.id)
    await _add(session, "Не связанная задача")

    subtasks = await repo.list_subtasks(1, parent.id)

    assert {t.id for t in subtasks} == {child1.id, child2.id}


async def test_list_subtasks_ignores_other_users(session):
    repo = TaskRepository(session)
    parent = await _add(session, "Эпик")
    await _add(session, "Чужая подзадача", telegram_user_id=2, parent_id=parent.id)

    subtasks = await repo.list_subtasks(1, parent.id)

    assert subtasks == []


async def test_top_level_only_excludes_subtasks(session):
    repo = TaskRepository(session)
    parent = await _add(session, "Эпик")
    await _add(session, "Подзадача", parent_id=parent.id)

    top_level = await repo.list_by_user(1, status="active", top_level_only=True)

    assert [t.id for t in top_level] == [parent.id]


async def test_count_subtasks_by_parents(session):
    repo = TaskRepository(session)
    parent1 = await _add(session, "Эпик 1")
    parent2 = await _add(session, "Эпик 2")
    await _add(session, "Подзадача 1.1", parent_id=parent1.id)
    await _add(session, "Подзадача 1.2", parent_id=parent1.id)
    await _add(session, "Подзадача 2.1", parent_id=parent2.id)

    counts = await repo.count_subtasks_by_parents(1, [parent1.id, parent2.id])

    assert counts == {parent1.id: 2, parent2.id: 1}


async def test_count_subtasks_by_parents_empty_list_returns_empty_dict(session):
    repo = TaskRepository(session)

    counts = await repo.count_subtasks_by_parents(1, [])

    assert counts == {}


async def test_count_subtasks_by_parents_omits_parents_without_children(session):
    repo = TaskRepository(session)
    parent = await _add(session, "Эпик без подзадач")

    counts = await repo.count_subtasks_by_parents(1, [parent.id])

    assert counts == {}
