"""
Регрессия: удаление привычки с логами не должно падать
ForeignKeyViolationError — habit_logs удаляются каскадно
(ON DELETE CASCADE, см. migrations/versions/007_cascade_delete_habit_logs.py).
"""

from datetime import date

import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.habits.models import Habit, HabitLog
from app.habits.repository import HabitRepository
from app.habits.service import HabitService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session

    await engine.dispose()


async def test_delete_habit_with_logs_does_not_raise(session):
    habit = Habit(telegram_user_id=1, title="Читать")
    session.add(habit)
    await session.commit()
    await session.refresh(habit)

    session.add(HabitLog(habit_id=habit.id, completed_on=date.today()))
    await session.commit()

    service = HabitService(HabitRepository(session))
    deleted = await service.delete_habit(1, habit.id)

    assert deleted is not None


async def test_delete_habit_removes_its_logs(session):
    habit = Habit(telegram_user_id=1, title="Читать")
    session.add(habit)
    await session.commit()
    await session.refresh(habit)

    session.add(HabitLog(habit_id=habit.id, completed_on=date.today()))
    await session.commit()

    service = HabitService(HabitRepository(session))
    await service.delete_habit(1, habit.id)

    remaining = await session.execute(
        select(HabitLog).where(HabitLog.habit_id == habit.id)
    )
    assert remaining.scalars().all() == []
