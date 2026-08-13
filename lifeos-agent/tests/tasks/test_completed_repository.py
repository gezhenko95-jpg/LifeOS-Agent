"""
Интеграционный тест TaskRepository.count_completed_since (по образцу
tests/tasks/test_reminders_repository.py) — нужен еженедельному
дайджесту (app/scheduler/weekly_digest.py).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.tasks.models import Task
from app.tasks.repository import TaskRepository

NOW = datetime.now(timezone.utc)
WEEK_AGO = NOW - timedelta(days=7)


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


async def test_counts_only_completed_within_period(session):
    await _add(
        session, status="completed", completed_at=NOW - timedelta(days=1)
    )  # в периоде
    await _add(
        session, status="completed", completed_at=WEEK_AGO - timedelta(days=1)
    )  # раньше периода
    await _add(session, status="active")  # не завершена

    repository = TaskRepository(session)
    count = await repository.count_completed_since(1, WEEK_AGO)

    assert count == 1


async def test_isolated_per_user(session):
    await _add(session, status="completed", completed_at=NOW)
    other_user_task = Task(
        telegram_user_id=2,
        title="Y",
        status="completed",
        completed_at=NOW,
    )
    session.add(other_user_task)
    await session.commit()

    repository = TaskRepository(session)
    count = await repository.count_completed_since(1, WEEK_AGO)

    assert count == 1


async def test_zero_when_nothing_completed(session):
    await _add(session, status="active")

    repository = TaskRepository(session)
    count = await repository.count_completed_since(1, WEEK_AGO)

    assert count == 0


async def test_count_completed_between_is_half_open_interval(session):
    await _add(
        session, status="completed", completed_at=WEEK_AGO
    )  # ровно на границе since — входит
    await _add(
        session, status="completed", completed_at=WEEK_AGO - timedelta(seconds=1)
    )  # чуть раньше since — не входит
    await _add(
        session, status="completed", completed_at=NOW
    )  # ровно на границе until — не входит (полуоткрытый интервал)

    repository = TaskRepository(session)
    count = await repository.count_completed_between(1, WEEK_AGO, NOW)

    assert count == 1


async def test_count_completed_between_isolated_per_user(session):
    await _add(session, status="completed", completed_at=NOW - timedelta(days=1))
    other_user_task = Task(
        telegram_user_id=2,
        title="Y",
        status="completed",
        completed_at=NOW - timedelta(days=1),
    )
    session.add(other_user_task)
    await session.commit()

    repository = TaskRepository(session)
    count = await repository.count_completed_between(1, NOW - timedelta(days=7), NOW)

    assert count == 1
