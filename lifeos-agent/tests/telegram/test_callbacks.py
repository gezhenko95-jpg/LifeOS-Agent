from unittest.mock import MagicMock

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.models import Contact
from app.db.base import Base
from app.digest.models import Digest
from app.finance.models import EXPENSE, INCOME, Transaction
from app.goals.models import Goal
from app.habits.models import Habit
from app.mood.models import MoodEntry
from app.tasks.models import Task
from app.tasks.repository import TaskCommentRepository, TaskRepository
from app.tasks.service import TaskCommentService
from app.telegram.callbacks import (
    _handle_contact_action,
    _handle_digest_action,
    _handle_finance_action,
    _handle_goal_action,
    _handle_habit_action,
    _handle_mood_action,
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


# --- Подзадачи/комментарии/"в работе" (specs/022-tasks-v2.md) --------------


async def test_task_action_i_toggles_in_progress(session):
    task = await _add_task(session)
    assert task.in_progress is False

    text, markup = await _handle_task_action(session, "i", str(task.id), 1, _context())

    assert "▶" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"t|i|{task.id}" in callbacks


async def test_task_action_a_asks_for_subtask_name(session):
    task = await _add_task(session)
    context = _context()

    text, markup = await _handle_task_action(session, "a", str(task.id), 1, context)

    assert "одзадач" in text
    assert context.user_data["pending_input"].kind == "task_subtask_add"
    assert context.user_data["pending_input"].task_id == task.id


async def test_task_action_k_asks_for_comment_text(session):
    task = await _add_task(session)
    context = _context()

    text, markup = await _handle_task_action(session, "k", str(task.id), 1, context)

    assert "омментари" in text
    assert context.user_data["pending_input"].kind == "task_comment_add"
    assert context.user_data["pending_input"].task_id == task.id


async def test_tasks_list_shows_subtask_and_comment_badges(session):
    parent = await _add_task(session)
    child = Task(
        telegram_user_id=1, title="Подзадача", status="active", parent_id=parent.id
    )
    session.add(child)
    await session.commit()
    comment_service = TaskCommentService(
        TaskCommentRepository(session), TaskRepository(session)
    )
    await comment_service.add_comment(1, parent.id, "Первый шаг")

    # "i" (переключить "в работе") — одно из действий, что перерисовывают
    # ВЕСЬ список (в отличие от "p"/"w", которые отвечают подтверждением
    # по одной задаче, см. _quick_action_result).
    text, _ = await _handle_task_action(session, "i", str(parent.id), 1, _context())

    assert "📎1" in text
    assert "💬1" in text


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


# --- Финансы (specs/017-finance.md) ---


async def _add_transaction(session, **kwargs) -> Transaction:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("kind", EXPENSE)
    kwargs.setdefault("category", "transport")
    kwargs.setdefault("amount", 500)
    transaction = Transaction(**kwargs)
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction


async def test_finance_menu(session):
    text, markup = await _handle_finance_action(session, "m", "", 1, _context())

    assert "Финансы" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["f|l", "f|n", "f|i"]


async def test_finance_action_n_opens_expense_prompt(session):
    context = _context()

    text, markup = await _handle_finance_action(session, "n", "", 1, context)

    assert "Сколько и на что" in text
    from app.telegram.pending_input import FINANCE_EXPENSE_ADD

    assert context.user_data["pending_input"].kind == FINANCE_EXPENSE_ADD


async def test_finance_action_i_opens_income_prompt(session):
    context = _context()

    text, markup = await _handle_finance_action(session, "i", "", 1, context)

    assert "Сколько получили" in text
    from app.telegram.pending_input import FINANCE_INCOME_ADD

    assert context.user_data["pending_input"].kind == FINANCE_INCOME_ADD


async def test_finance_action_l_lists_transactions_and_summary(session):
    await _add_transaction(session, kind=EXPENSE, category="transport", amount=500)
    await _add_transaction(session, kind=INCOME, category=None, amount=80000)

    text, markup = await _handle_finance_action(session, "l", "", 1, _context())

    assert "💸 500" in text
    assert "💰 80 000" in text
    assert "Доход: 80 000" in text


async def test_finance_action_x_deletes_transaction(session):
    transaction = await _add_transaction(session)

    text, markup = await _handle_finance_action(
        session, "x", str(transaction.id), 1, _context()
    )

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"f|x|{transaction.id}" not in callbacks
    assert "🪙" not in text  # удаление не награждается


async def test_finance_action_x_wrong_owner_does_not_delete(session):
    transaction = await _add_transaction(session, telegram_user_id=2)

    await _handle_finance_action(session, "x", str(transaction.id), 1, _context())

    from sqlalchemy import select

    result = await session.execute(select(Transaction))
    assert len(result.scalars().all()) == 1  # чужая транзакция никуда не делась


# --- Люди / личный CRM (specs/018-personal-crm.md) ---


async def _add_contact(session, **kwargs) -> Contact:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("name", "Аня")
    contact = Contact(**kwargs)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def test_contacts_menu(session):
    text, markup = await _handle_contact_action(session, "m", "", 1, _context())

    assert "Люди" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["c|l", "c|n"]


async def test_contact_action_n_opens_add_prompt(session):
    context = _context()

    text, markup = await _handle_contact_action(session, "n", "", 1, context)

    assert "Кого добавляем" in text
    from app.telegram.pending_input import CONTACT_ADD

    assert context.user_data["pending_input"].kind == CONTACT_ADD


async def test_contact_action_l_lists_contacts(session):
    await _add_contact(session, name="Аня")

    text, markup = await _handle_contact_action(session, "l", "", 1, _context())

    assert "Аня" in text


async def test_contact_action_d_marks_contacted_and_rewards(session):
    from datetime import datetime, timedelta, timezone

    contact = await _add_contact(
        session, last_contact_at=datetime.now(timezone.utc) - timedelta(days=40)
    )

    text, markup = await _handle_contact_action(
        session, "d", str(contact.id), 1, _context()
    )

    assert "🪙" in text  # "написал(а)" — сделал-действие, награждается


async def test_contact_action_x_deletes_contact_without_reward(session):
    contact = await _add_contact(session)

    text, markup = await _handle_contact_action(
        session, "x", str(contact.id), 1, _context()
    )

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"c|x|{contact.id}" not in callbacks
    assert "🪙" not in text  # удаление не награждается


async def test_contact_action_x_wrong_owner_does_not_delete(session):
    from sqlalchemy import select

    contact = await _add_contact(session, telegram_user_id=2)

    await _handle_contact_action(session, "x", str(contact.id), 1, _context())

    result = await session.execute(select(Contact))
    assert len(result.scalars().all()) == 1  # чужой контакт никуда не делся


# --- Настроение (specs/019-mood-tracker.md) ----------------------------


def _query(text: str = "Как прошёл день?") -> MagicMock:
    query = MagicMock()
    query.message.text = text
    return query


async def _add_mood(session, **kwargs) -> MoodEntry:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("score", 3)
    entry = MoodEntry(**kwargs)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_mood_menu(session):
    text, markup = await _handle_mood_action(session, "m", "", 1, _query())

    assert "Настроение" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["m|s|1", "m|s|2", "m|s|3", "m|s|4", "m|s|5", "m|l"]


async def test_mood_action_s_logs_score_and_appends_to_original_text(session):
    text, markup = await _handle_mood_action(
        session, "s", "4", 1, _query("Как прошёл день?")
    )

    assert text.startswith("Как прошёл день?")
    assert "4/5" in text
    assert "🪙" in text  # награда — "сделал"-действие
    assert len(markup.inline_keyboard) == 0  # кнопка снята, повторный тап невозможен


async def test_mood_action_l_lists_entries(session):
    await _add_mood(session, score=5)

    text, markup = await _handle_mood_action(session, "l", "", 1, _query())

    assert "5/5" in text


async def test_mood_action_x_deletes_entry_without_reward(session):
    entry = await _add_mood(session)

    text, markup = await _handle_mood_action(session, "x", str(entry.id), 1, _query())

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"m|x|{entry.id}" not in callbacks
    assert "🪙" not in text


async def test_mood_action_x_wrong_owner_does_not_delete(session):
    from sqlalchemy import select

    entry = await _add_mood(session, telegram_user_id=2)

    await _handle_mood_action(session, "x", str(entry.id), 1, _query())

    result = await session.execute(select(MoodEntry))
    assert len(result.scalars().all()) == 1  # чужая запись никуда не делась
