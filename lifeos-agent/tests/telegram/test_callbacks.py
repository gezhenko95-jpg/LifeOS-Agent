import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.tasks.models import Task
from app.telegram.callbacks import (
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

    text, markup = await _handle_task_action(session, "p", str(task.id), 1)

    assert "❗" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"t|p|{task.id}" not in callbacks  # уже важная — кнопка убрана
    assert f"t|w|{task.id}" in callbacks


async def test_quick_action_w_sets_tomorrow_due_date(session):
    task = await _add_task(session)

    text, markup = await _handle_task_action(session, "w", str(task.id), 1)

    assert "на " in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"t|w|{task.id}" not in callbacks  # дата уже есть — кнопка убрана
    assert f"t|p|{task.id}" in callbacks


async def test_quick_action_on_missing_task_is_graceful(session):
    text, markup = await _handle_task_action(session, "p", "999999", 1)

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

    text, markup = await _handle_watchlist_action(session, "d", str(item.id), 1)

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"w|d|{item.id}" not in callbacks


async def test_watchlist_action_x_deletes_and_removes_from_list(session):
    item = await _add_watchlist_item(session)

    text, markup = await _handle_watchlist_action(session, "x", str(item.id), 1)

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"w|x|{item.id}" not in callbacks


async def test_watchlist_action_r_recommends_without_ai(session):
    await _add_watchlist_item(session)

    text, markup = await _handle_watchlist_action(session, "r", "0", 1)

    assert "Как насчёт" in text
    assert len(markup.inline_keyboard) == 0


async def test_watchlist_action_r_on_empty_list(session):
    text, markup = await _handle_watchlist_action(session, "r", "0", 1)

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
