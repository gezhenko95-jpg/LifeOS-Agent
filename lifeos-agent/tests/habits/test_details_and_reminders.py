"""
Описание, редактирование и напоминания привычек (миграция 015) плюс
каталог готовых привычек (app/habits/templates.py).
"""

from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.base import Base
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.habits.templates import HABIT_TEMPLATES, get_template
from tests.support import sqlite_engine

OWNER = 414825951
STRANGER = 999


@pytest_asyncio.fixture
async def service():
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield HabitService(HabitRepository(session))

    await engine.dispose()


# --- Описание и редактирование --------------------------------------------


async def test_habit_can_be_created_with_description_and_reminder(service):
    habit = await service.create_habit(OWNER, "Зарядка", "10 минут утром", time(8, 0))

    assert habit.description == "10 минут утром"
    assert habit.reminder_time == time(8, 0)


async def test_empty_description_is_stored_as_none(service):
    """Пустая строка и «нет описания» — одно и то же состояние, иначе в
    интерфейсе появится пустая строка-подпись."""
    habit = await service.create_habit(OWNER, "Зарядка", "   ")

    assert habit.description is None


async def test_update_changes_only_what_was_passed(service):
    habit = await service.create_habit(OWNER, "Зарядка", "10 минут", time(8, 0))

    updated = await service.update_habit(OWNER, habit.id, title="Зарядка утром")

    assert updated.title == "Зарядка утром"
    # Главное: правка названия не сбила напоминание и описание.
    assert updated.description == "10 минут"
    assert updated.reminder_time == time(8, 0)


async def test_reminder_is_cleared_only_by_explicit_flag(service):
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))

    updated = await service.update_habit(OWNER, habit.id, clear_reminder=True)

    assert updated.reminder_time is None


async def test_description_is_cleared_only_by_explicit_flag(service):
    habit = await service.create_habit(OWNER, "Зарядка", "10 минут")

    updated = await service.update_habit(OWNER, habit.id, clear_description=True)

    assert updated.description is None


async def test_update_rejects_empty_title(service):
    habit = await service.create_habit(OWNER, "Зарядка")

    with pytest.raises(ValueError):
        await service.update_habit(OWNER, habit.id, title="   ")


async def test_stranger_cannot_edit_someone_elses_habit(service):
    habit = await service.create_habit(OWNER, "Зарядка")

    assert await service.update_habit(STRANGER, habit.id, title="Взлом") is None


async def test_new_reminder_time_resets_today_reminded_mark(service):
    """Переставили время на попозже в тот же день — напоминание должно
    сработать, а не «уже напоминали сегодня»."""
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))
    await service.mark_reminded(habit)

    updated = await service.update_habit(OWNER, habit.id, reminder_time=time(20, 0))

    assert updated.last_reminded_on is None


# --- Напоминания ----------------------------------------------------------


async def test_reminder_is_due_when_time_has_come(service):
    await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))

    due = await service.list_due_reminders(now=time(8, 30), today=date.today())

    assert [h.title for h in due] == ["Зарядка"]


async def test_reminder_is_not_due_before_its_time(service):
    await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))

    assert await service.list_due_reminders(now=time(7, 0), today=date.today()) == []


async def test_habit_without_reminder_time_is_never_due(service):
    await service.create_habit(OWNER, "Зарядка")

    assert await service.list_due_reminders(now=time(23, 59), today=date.today()) == []


async def test_habit_done_today_is_not_reminded(service):
    """Напоминать о том, что человек уже сделал, — верный способ
    приучить игнорировать напоминания."""
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))
    await service.mark_done_by_id(OWNER, habit.id)

    due = await service.list_due_reminders(now=time(9, 0), today=date.today())

    assert due == []


async def test_reminder_is_sent_once_per_day(service):
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))
    today = date.today()

    first = await service.list_due_reminders(now=time(8, 30), today=today)
    await service.mark_reminded(habit, today)
    second = await service.list_due_reminders(now=time(8, 31), today=today)

    assert len(first) == 1
    assert second == []


async def test_reminder_returns_next_day(service):
    """Ежедневная привычка — вчерашняя отметка «напомнили» не должна
    глушить сегодняшнее напоминание."""
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))
    today = date.today()
    await service.mark_reminded(habit, today - timedelta(days=1))

    due = await service.list_due_reminders(now=time(8, 30), today=today)

    assert len(due) == 1


async def test_archived_habit_is_not_reminded(service):
    habit = await service.create_habit(OWNER, "Зарядка", reminder_time=time(8, 0))
    habit.archived = True
    await service._repository.save(habit)

    assert await service.list_due_reminders(now=time(9, 0), today=date.today()) == []


# --- Шаблоны --------------------------------------------------------------


async def test_template_creates_ready_habit(service):
    template = get_template("water")

    habit = await service.create_from_template(OWNER, template)

    assert habit.title == template.title
    assert habit.description == template.description
    assert habit.reminder_time == template.reminder_time


def test_unknown_template_returns_none():
    """slug приходит из кнопки, которая могла остаться от прошлой версии
    бота — падать на этом нельзя."""
    assert get_template("no-such-template") is None


def test_template_slugs_are_unique():
    slugs = [template.slug for template in HABIT_TEMPLATES]

    assert len(slugs) == len(set(slugs))


def test_template_slugs_fit_callback_data():
    """slug ездит в callback_data («h|a|{slug}»), где у Telegram лимит
    64 байта, и должен быть ASCII — кириллица съела бы его вдвое."""
    for template in HABIT_TEMPLATES:
        payload = f"h|a|{template.slug}"
        assert len(payload.encode("utf-8")) <= 64
        assert template.slug.isascii()


# --- Кнопки бота ----------------------------------------------------------


def test_templates_screen_offers_every_template():
    from app.telegram.keyboards import build_habit_templates_message

    text, markup = build_habit_templates_message()
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]

    for template in HABIT_TEMPLATES:
        assert template.title in text
        assert f"h|a|{template.slug}" in callbacks
    # Из каталога всегда можно вернуться на экран раздела.
    assert callbacks[-1] == "h|m"


def test_habits_section_offers_templates():
    from app.telegram.keyboards import build_habits_menu

    _, markup = build_habits_menu()
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]

    assert callbacks == ["h|l", "h|n", "h|t"]
