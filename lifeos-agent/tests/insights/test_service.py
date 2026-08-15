"""
InsightsService.build_findings — композиция Tasks/Habits/Memory
(см. specs/009-personal-insights.md). Мокнутые сервисы для сборки/
граничных случаев + один интеграционный тест на SQLite in-memory,
проверяющий, что реальная связка сервисов не падает.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.habits.models import Habit
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.insights.service import InsightsService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService

NOW = datetime.now(timezone.utc)

# --- Мокнутые сервисы: сборка и граничные случаи --------------------------


def _empty_services() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    task_service = AsyncMock()
    task_service.list_tasks_completed_between.return_value = []
    habit_service = AsyncMock()
    habit_service.list_active_habits.return_value = []
    memory_service = AsyncMock()
    return task_service, habit_service, memory_service


async def test_empty_database_returns_no_findings():
    task_service, habit_service, memory_service = _empty_services()
    service = InsightsService(task_service, habit_service, memory_service)

    findings = await service.build_findings(1)

    assert findings == []


async def test_longest_streak_finding_present_without_tasks():
    task_service, habit_service, memory_service = _empty_services()
    habit = Habit(id=1, telegram_user_id=1, title="Чтение")
    habit_service.list_active_habits.return_value = [habit]
    habit_service.get_completed_days_bulk.return_value = {1: set()}
    habit_service.get_longest_streaks_bulk.return_value = {1: 5}
    memory_service.list_journal_entries_since.return_value = []
    service = InsightsService(task_service, habit_service, memory_service)

    findings = await service.build_findings(1)

    assert any("Рекорд серии" in finding for finding in findings)
    assert any("Чтение" in finding for finding in findings)


async def test_no_habits_skips_journal_and_streak_findings():
    task_service, habit_service, memory_service = _empty_services()
    service = InsightsService(task_service, habit_service, memory_service)

    findings = await service.build_findings(1)

    assert not any("Рекорд серии" in finding for finding in findings)
    assert not any("дневник" in finding for finding in findings)
    memory_service.list_journal_entries_since.assert_not_called()


# --- Интеграционный тест на реальной связке сервисов -----------------------


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _real_services(session) -> InsightsService:
    return InsightsService(
        TaskService(TaskRepository(session)),
        HabitService(HabitRepository(session)),
        MemoryService(MemoryRepository(session)),
    )


async def test_real_services_empty_database_does_not_crash(session):
    service = _real_services(session)

    findings = await service.build_findings(1)

    assert findings == []


async def test_real_services_with_data_does_not_crash(session):
    # Одна привычка с несколькими логами — достаточно, чтобы задеть все
    # ветки (журнал/стрик), не заботясь о порогах остальных находок.
    habit = Habit(telegram_user_id=1, title="Спорт")
    session.add(habit)
    await session.commit()
    await session.refresh(habit)

    habit_repository = HabitRepository(session)
    today = date.today()
    for offset in range(3):
        await habit_repository.add_log(habit.id, today - timedelta(days=offset))

    task = Task(
        telegram_user_id=1,
        title="Сделать отчёт",
        status="completed",
        completed_at=NOW - timedelta(days=1),
    )
    session.add(task)
    await session.commit()

    service = _real_services(session)
    findings = await service.build_findings(1)

    assert any("Рекорд серии" in finding for finding in findings)
