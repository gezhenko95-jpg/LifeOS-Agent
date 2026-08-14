"""
Обработка нажатий на inline-кнопки (см. app/telegram/keyboards.py).
"""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
from app.telegram.keyboards import (
    build_goals_message,
    build_habits_message,
    build_task_confirmation_message,
    build_tasks_message,
    build_watchlist_message,
)
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService

# 9:00 — тот же час по умолчанию, что и у date_parser.py для дат без
# явного времени (не импортируем оттуда приватную константу).
_DEFAULT_HOUR = 9

logger = logging.getLogger(__name__)


def parse_callback(data: str) -> tuple[str, str, str] | None:
    """ "t|c|5" -> ("t", "c", "5"). Отдельная чистая функция для тестов.

    None на мусорном значении: раньше строка без "|" роняла распаковку
    (ValueError), а исключение уходило в лог, оставляя пользователя без
    ответа (см. AUDIT.md, B-3).
    """
    domain, _, rest = data.partition("|")
    action, _, item_id = rest.partition("|")
    if not domain or not action:
        return None
    return domain, action, item_id


def _parse_item_id(item_id: str) -> int | None:
    """None вместо ValueError на нечисловом id (см. parse_callback)."""
    try:
        return int(item_id)
    except ValueError:
        return None


async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    # У CallbackQueryHandler нет параметра filters (в отличие от
    # Message/CommandHandler, см. app/telegram/bot.py), поэтому владельца
    # проверяем здесь. Без проверки посторонний мог перебором id
    # выполнять и удалять чужие задачи/привычки/цели — id приходит прямо
    # из callback_data (см. AUDIT.md, C-4/B-2).
    owner_id = get_settings().owner_telegram_user_id
    if owner_id and update.effective_user.id != owner_id:
        await query.answer("Этот бот личный.", show_alert=True)
        return

    await query.answer()

    parsed = parse_callback(query.data)
    if parsed is None:
        return
    domain, action, item_id = parsed
    if domain == "g" and action == "noop":
        return

    # "w|r|0" ("Порекомендуй") действует на весь список, id ему не нужен —
    # всем остальным действиям нужен корректный числовой id.
    is_idless_action = domain == "w" and action == "r"
    if not is_idless_action and _parse_item_id(item_id) is None:
        return

    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        if domain == "t":
            text, markup = await _handle_task_action(
                session, action, item_id, telegram_user_id
            )
        elif domain == "h":
            text, markup = await _handle_habit_action(
                session, action, item_id, telegram_user_id
            )
        elif domain == "g":
            text, markup = await _handle_goal_action(
                session, action, item_id, telegram_user_id
            )
        elif domain == "w":
            text, markup = await _handle_watchlist_action(
                session, action, item_id, telegram_user_id
            )
        else:
            return

    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        # "Message is not modified" — обычный двойной тап по кнопке, когда
        # результат не изменился (например, повторное «готово» на уже
        # отмеченной привычке). Это не ошибка, ронять хендлер незачем
        # (см. AUDIT.md, B-4).
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Сообщение не изменилось, перерисовка пропущена")


async def _handle_task_action(
    session: AsyncSession, action: str, item_id: str, telegram_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    service = TaskService(TaskRepository(session))

    if action == "p":
        task = await service.update_task(int(item_id), priority="high")
        return _quick_action_result(task)
    if action == "w":
        tomorrow = datetime.combine(
            date.today() + timedelta(days=1), time(hour=_DEFAULT_HOUR)
        ).astimezone()
        task = await service.update_task(int(item_id), due_date=tomorrow)
        return _quick_action_result(task)

    if action == "c":
        await service.update_task(int(item_id), status="completed")
    elif action == "d":
        await service.delete_task(int(item_id))
    tasks = await service.list_active_tasks(telegram_user_id)
    return build_tasks_message(tasks)


def _quick_action_result(task: Task | None) -> tuple[str, InlineKeyboardMarkup]:
    if task is None:
        # Задачу успели удалить/завершить, пока кнопка ещё была на экране.
        return "Задача больше не активна.", InlineKeyboardMarkup([])
    return build_task_confirmation_message(task)


async def _handle_habit_action(
    session: AsyncSession, action: str, item_id: str, telegram_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    service = HabitService(HabitRepository(session))
    if action == "d":
        await service.mark_done_by_id(int(item_id))
    elif action == "x":
        await service.delete_habit(int(item_id))
    habits = await service.list_active_habits(telegram_user_id)
    streaks = {habit.id: await service.get_streak(habit.id) for habit in habits}
    return build_habits_message(habits, streaks)


async def _handle_goal_action(
    session: AsyncSession, action: str, item_id: str, telegram_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    service = GoalService(GoalRepository(session))
    if action in ("u", "n"):
        goals = await service.list_active_goals(telegram_user_id)
        goal = next((g for g in goals if g.id == int(item_id)), None)
        if goal is not None:
            delta = 10 if action == "u" else -10
            new_progress = max(0, min(100, goal.progress + delta))
            await service.update_progress(goal.id, new_progress)
    elif action == "c":
        await service.complete_goal(int(item_id))
    elif action == "x":
        await service.delete_goal(int(item_id))
    goals = await service.list_active_goals(telegram_user_id)
    return build_goals_message(goals)


async def _handle_watchlist_action(
    session: AsyncSession, action: str, item_id: str, telegram_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    service = WatchlistService(WatchlistRepository(session))
    if action == "d":
        await service.mark_done(int(item_id))
    elif action == "x":
        await service.delete_item(int(item_id))
    elif action == "r":
        recommendation = await service.pick_recommendation(
            telegram_user_id, get_ai_client()
        )
        text = recommendation or "Смотреть/читать пока нечего."
        return text, InlineKeyboardMarkup([])

    items = await service.list_active_items(telegram_user_id)
    return build_watchlist_message(items)
