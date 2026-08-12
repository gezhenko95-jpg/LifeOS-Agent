"""
Интеграционный тест TaskRepository.list_due_unreminded.

Для этой логики нет REST-эндпоинта (это внутренняя механика Scheduler),
поэтому тестируем репозиторий напрямую на SQLite в памяти — как
tests/tasks/test_api.py, но без HTTP-слоя.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.tasks.models import Task
from app.tasks.repository import TaskRepository

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _add(session, **kwargs) -> Task:
    kwargs.setdefault("status", "active")
    task = Task(telegram_user_id=1, title="X", **kwargs)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_returns_only_due_and_unreminded(session):
    due_task = await _add(session, due_date=NOW - timedelta(minutes=1))
    future_task = await _add(session, due_date=NOW + timedelta(hours=1))
    already_reminded = await _add(
        session, due_date=NOW - timedelta(minutes=1), reminded_at=NOW
    )
    no_due_date_task = await _add(session, due_date=None)

    repository = TaskRepository(session)
    result = await repository.list_due_unreminded(NOW)

    result_ids = {task.id for task in result}
    assert due_task.id in result_ids
    assert future_task.id not in result_ids
    assert already_reminded.id not in result_ids
    assert no_due_date_task.id not in result_ids


async def test_excludes_completed_tasks(session):
    completed = await _add(
        session, due_date=NOW - timedelta(minutes=1), status="completed"
    )

    repository = TaskRepository(session)
    result = await repository.list_due_unreminded(NOW)

    assert completed.id not in {task.id for task in result}


async def test_empty_when_nothing_due(session):
    await _add(session, due_date=NOW + timedelta(hours=1))

    repository = TaskRepository(session)
    result = await repository.list_due_unreminded(NOW)

    assert result == []
