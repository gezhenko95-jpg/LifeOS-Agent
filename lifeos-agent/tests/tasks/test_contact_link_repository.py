"""TaskRepository.list_by_contact — против настоящей SQLite."""

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


async def _add_task(session, telegram_user_id=1, contact_id=None) -> Task:
    task = Task(
        telegram_user_id=telegram_user_id,
        title="Задача",
        status="active",
        contact_id=contact_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_list_by_contact_returns_only_linked_tasks(session):
    linked = await _add_task(session, contact_id=5)
    await _add_task(session, contact_id=None)
    await _add_task(session, contact_id=9)

    tasks = await TaskRepository(session).list_by_contact(1, contact_id=5)

    assert [t.id for t in tasks] == [linked.id]


async def test_list_by_contact_ignores_other_users(session):
    await _add_task(session, telegram_user_id=2, contact_id=5)

    tasks = await TaskRepository(session).list_by_contact(1, contact_id=5)

    assert tasks == []


async def test_list_by_contact_no_matches_returns_empty_list(session):
    tasks = await TaskRepository(session).list_by_contact(1, contact_id=999)

    assert tasks == []
