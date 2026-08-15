"""
HabitRepository — против настоящей БД (SQLite в памяти), в отличие от
tests/habits/test_service.py, где репозиторий замокан. Здесь важно
именно число запросов, а не только результат.
"""

from datetime import date

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.habits.models import Habit, HabitLog
from app.habits.repository import HabitRepository
from tests.support import sqlite_engine

TODAY = date.today()


@pytest_asyncio.fixture
async def session():
    # sqlite_engine (не create_async_engine напрямую) — find_active_by_title
    # использует ILIKE, а встроенный lower() у SQLite не понимает кириллицу
    # (см. tests/support.py).
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add_habit(session, title="Читать") -> Habit:
    habit = Habit(telegram_user_id=1, title=title)
    session.add(habit)
    await session.commit()
    await session.refresh(habit)
    return habit


async def _add_log(session, habit_id: int, day: date) -> None:
    session.add(HabitLog(habit_id=habit_id, completed_on=day))
    await session.commit()


async def test_list_logs_for_habits_groups_by_habit(session):
    """Основной сценарий: логи нескольких привычек одним запросом (см.
    AUDIT.md, P-1) — без него список привычек делал бы по запросу на
    каждую в цикле."""
    from datetime import timedelta

    habit_a = await _add_habit(session, "Читать")
    habit_b = await _add_habit(session, "Спорт")
    await _add_log(session, habit_a.id, TODAY)
    await _add_log(session, habit_a.id, TODAY - timedelta(days=1))
    await _add_log(session, habit_b.id, TODAY)

    repo = HabitRepository(session)
    grouped = await repo.list_logs_for_habits([habit_a.id, habit_b.id])

    assert set(grouped.keys()) == {habit_a.id, habit_b.id}
    assert len(grouped[habit_a.id]) == 2
    assert len(grouped[habit_b.id]) == 1


async def test_list_logs_for_habits_omits_ids_without_logs(session):
    """Привычка без единого лога не попадает в словарь ключом вообще —
    вызывающий код (HabitService) обязан использовать .get(id, ...),
    а не [id]."""
    habit = await _add_habit(session)

    repo = HabitRepository(session)
    grouped = await repo.list_logs_for_habits([habit.id])

    assert grouped == {}


async def test_list_logs_for_habits_only_returns_requested_ids(session):
    """Логи привычки, не попавшей в запрос, не должны просачиваться в
    результат — иначе стрик одной привычки мог бы посчитаться по чужим
    отметкам."""
    habit_a = await _add_habit(session, "Читать")
    habit_b = await _add_habit(session, "Спорт")
    await _add_log(session, habit_a.id, TODAY)
    await _add_log(session, habit_b.id, TODAY)

    repo = HabitRepository(session)
    grouped = await repo.list_logs_for_habits([habit_a.id])

    assert set(grouped.keys()) == {habit_a.id}


async def test_list_logs_for_habits_empty_input_returns_empty_without_querying(
    session,
):
    repo = HabitRepository(session)

    grouped = await repo.list_logs_for_habits([])

    assert grouped == {}


async def test_list_logs_for_habits_result_matches_list_logs_per_habit(session):
    """Пакетный и одиночный метод должны видеть одни и те же логи —
    иначе список привычек и подтверждение после отметки покажут разные
    цифры для одной и той же привычки (см. AUDIT.md, P-1)."""
    habit = await _add_habit(session)
    await _add_log(session, habit.id, TODAY)
    await _add_log(session, habit.id, date(TODAY.year, TODAY.month, 1))

    repo = HabitRepository(session)
    single = await repo.list_logs(habit.id)
    bulk = await repo.list_logs_for_habits([habit.id])

    single_days = {log.completed_on for log in single}
    bulk_days = {log.completed_on for log in bulk[habit.id]}
    assert single_days == bulk_days


# --- find_active_by_title: фильтр в БД, не в Python (AUDIT.md, P-2) ---


async def test_find_active_by_title_case_insensitive_cyrillic(session):
    """SQLite не понимает регистр кириллицы без tests/support.sqlite_engine
    (см. её докстринг) — этот тест провалился бы молча, если бы конфтест
    случайно потерял хук."""
    await _add_habit(session, "Читать книгу")
    repo = HabitRepository(session)

    matches = await repo.find_active_by_title(1, "КНИГУ")

    assert len(matches) == 1


async def test_find_active_by_title_excludes_archived(session):
    habit = await _add_habit(session, "Читать")
    habit.archived = True
    await session.commit()
    repo = HabitRepository(session)

    matches = await repo.find_active_by_title(1, "читать")

    assert matches == []


async def test_find_active_by_title_percent_is_literal(session):
    await _add_habit(session, "100% сфокусироваться")
    repo = HabitRepository(session)

    matches = await repo.find_active_by_title(1, "100%")

    assert len(matches) == 1
