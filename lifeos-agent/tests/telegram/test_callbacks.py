from unittest.mock import MagicMock

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.digest.models import Digest
from app.goals.models import Goal
from app.habits.models import Habit
from app.tasks.models import Task
from app.telegram.callbacks import (
    _handle_digest_action,
    _handle_goal_action,
    _handle_habit_action,
    _handle_task_action,
    _handle_watchlist_action,
    parse_callback,
)
from app.watchlist.models import WatchlistItem


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _context() -> MagicMock:
    """Кнопкам раздела нужен context — в нём живёт ожидание ввода
    (см. app/telegram/pending_input.py). Действиям над сущностями он не
    нужен, но сигнатура одна на все."""
    context = MagicMock()
    context.user_data = {}
    return context


async def _add_task(session, **kwargs) -> Task:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("priority", "normal")
    task = Task(telegram_user_id=1, title="Купить молоко", **kwargs)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def test_quick_action_p_sets_high_priority(session):
    task = await _add_task(session)

    text, markup = await _handle_task_action(session, "p", str(task.id), 1, _context())

    assert "❗" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"t|p|{task.id}" not in callbacks  # уже важная — кнопка убрана
    assert f"t|w|{task.id}" in callbacks


async def test_quick_action_w_sets_tomorrow_due_date(session):
    task = await _add_task(session)

    text, markup = await _handle_task_action(session, "w", str(task.id), 1, _context())

    assert "на " in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"t|w|{task.id}" not in callbacks  # дата уже есть — кнопка убрана
    assert f"t|p|{task.id}" in callbacks


async def test_quick_action_on_missing_task_is_graceful(session):
    text, markup = await _handle_task_action(session, "p", "999999", 1, _context())

    assert "не активна" in text
    assert len(markup.inline_keyboard) == 0


async def _add_watchlist_item(session, **kwargs) -> WatchlistItem:
    kwargs.setdefault("media_type", "movie")
    item = WatchlistItem(telegram_user_id=1, title="Дюна", **kwargs)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def test_watchlist_action_d_marks_done_and_removes_from_list(session):
    item = await _add_watchlist_item(session)

    text, markup = await _handle_watchlist_action(
        session, "d", str(item.id), 1, _context()
    )

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"w|d|{item.id}" not in callbacks


async def test_watchlist_action_x_deletes_and_removes_from_list(session):
    item = await _add_watchlist_item(session)

    text, markup = await _handle_watchlist_action(
        session, "x", str(item.id), 1, _context()
    )

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"w|x|{item.id}" not in callbacks


async def test_watchlist_action_r_recommends_without_ai(session):
    await _add_watchlist_item(session)

    text, markup = await _handle_watchlist_action(session, "r", "0", 1, _context())

    assert "Как насчёт" in text
    assert len(markup.inline_keyboard) == 0


async def test_watchlist_action_r_on_empty_list(session):
    text, markup = await _handle_watchlist_action(session, "r", "0", 1, _context())

    assert "нечего" in text


def test_parse_task_complete():
    assert parse_callback("t|c|5") == ("t", "c", "5")


def test_parse_task_delete():
    assert parse_callback("t|d|42") == ("t", "d", "42")


def test_parse_habit_action():
    assert parse_callback("h|x|7") == ("h", "x", "7")


def test_parse_goal_action():
    assert parse_callback("g|u|1") == ("g", "u", "1")


def test_parse_goal_noop_has_no_id():
    assert parse_callback("g|noop") == ("g", "noop", "")


# --- Награда за "сделал"-действия по кнопкам (specs/016-engagement-hooks.md) ---


async def test_task_complete_shows_reward_once_per_day(session):
    task = await _add_task(session)

    text, _ = await _handle_task_action(session, "c", str(task.id), 1, _context())
    assert "🪙" in text

    task2 = await _add_task(session)
    text2, _ = await _handle_task_action(session, "c", str(task2.id), 1, _context())
    assert "🪙" not in text2  # тот же день, уже награждено


async def test_task_complete_missing_task_no_reward(session):
    text, _ = await _handle_task_action(session, "c", "999999", 1, _context())

    assert "🪙" not in text


async def _add_habit(session, **kwargs) -> Habit:
    habit = Habit(telegram_user_id=1, title="Читать", **kwargs)
    session.add(habit)
    await session.commit()
    await session.refresh(habit)
    return habit


async def test_habit_done_shows_reward(session):
    habit = await _add_habit(session)

    text, _ = await _handle_habit_action(session, "d", str(habit.id), 1, _context())

    assert "🪙" in text


async def test_habit_done_missing_habit_no_reward(session):
    text, _ = await _handle_habit_action(session, "d", "999999", 1, _context())

    assert "🪙" not in text


async def _add_goal(session, **kwargs) -> Goal:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("progress", 0)
    goal = Goal(telegram_user_id=1, title="Испанский", **kwargs)
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


async def test_goal_progress_up_shows_reward(session):
    goal = await _add_goal(session)

    text, _ = await _handle_goal_action(session, "u", str(goal.id), 1, _context())

    assert "🪙" in text


async def test_goal_progress_down_no_reward(session):
    """Откат прогресса назад — не награждается, в отличие от роста."""
    goal = await _add_goal(session, progress=50)

    text, _ = await _handle_goal_action(session, "p", str(goal.id), 1, _context())

    assert "🪙" not in text


async def test_goal_complete_shows_reward(session):
    goal = await _add_goal(session)

    text, _ = await _handle_goal_action(session, "c", str(goal.id), 1, _context())

    assert "🪙" in text


async def test_watchlist_done_shows_reward(session):
    item = await _add_watchlist_item(session)

    text, _ = await _handle_watchlist_action(session, "d", str(item.id), 1, _context())

    assert "🪙" in text


async def _add_digest(session, **kwargs) -> Digest:
    digest = Digest(telegram_user_id=1, name="ESG", **kwargs)
    session.add(digest)
    await session.commit()
    await session.refresh(digest)
    return digest


def _query_with_message(text: str) -> MagicMock:
    query = MagicMock()
    query.message.text = text
    return query


async def test_digest_save_creates_memory_entry_and_reward(session):
    digest = await _add_digest(session)
    query = _query_with_message("Сегодня в ESG: важная новость.")

    text, markup = await _handle_digest_action(
        session, "f", str(digest.id), 1, _context(), query
    )

    assert "сохранён" in text
    assert "🪙" in text
    assert len(markup.inline_keyboard) == 0  # кнопка снята — повторно не нажать

    from sqlalchemy import select

    from app.memory.models import MemoryEntry

    result = await session.execute(select(MemoryEntry))
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].content == "Сегодня в ESG: важная новость."
    assert entries[0].source == "digest_save"


async def test_digest_save_without_message_text_is_graceful(session):
    digest = await _add_digest(session)
    query = _query_with_message("")

    text, markup = await _handle_digest_action(
        session, "f", str(digest.id), 1, _context(), query
    )

    assert "Нечего сохранять" in text
    assert len(markup.inline_keyboard) == 0
