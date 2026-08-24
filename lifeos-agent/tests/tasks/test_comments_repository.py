"""TaskCommentRepository — против настоящей SQLite."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.tasks.models import Task, TaskComment
from app.tasks.repository import TaskCommentRepository
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


async def _add_task(session, telegram_user_id=1) -> Task:
    task = Task(telegram_user_id=telegram_user_id, title="Задача", status="active")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _add_comment(session, task_id, text, telegram_user_id=1) -> TaskComment:
    comment = TaskComment(task_id=task_id, telegram_user_id=telegram_user_id, text=text)
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def test_list_by_task_orders_by_created_at(session):
    task = await _add_task(session)
    first = await _add_comment(session, task.id, "Первый")
    second = await _add_comment(session, task.id, "Второй")

    comments = await TaskCommentRepository(session).list_by_task(task.id)

    assert [c.id for c in comments] == [first.id, second.id]


async def test_list_by_task_ignores_other_tasks(session):
    task1 = await _add_task(session)
    task2 = await _add_task(session)
    await _add_comment(session, task1.id, "Комментарий к задаче 1")

    comments = await TaskCommentRepository(session).list_by_task(task2.id)

    assert comments == []


async def test_count_by_tasks(session):
    task1 = await _add_task(session)
    task2 = await _add_task(session)
    await _add_comment(session, task1.id, "1")
    await _add_comment(session, task1.id, "2")
    await _add_comment(session, task2.id, "3")

    counts = await TaskCommentRepository(session).count_by_tasks([task1.id, task2.id])

    assert counts == {task1.id: 2, task2.id: 1}


async def test_count_by_tasks_empty_list_returns_empty_dict(session):
    counts = await TaskCommentRepository(session).count_by_tasks([])

    assert counts == {}
