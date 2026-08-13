"""
Фоновые задачи Telegram-бота (Scheduler), см. flows/001-morning-briefing.md.
"""

import logging

from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.proactive.repository import PendingPromptRepository
from app.proactive.service import PendingPromptService
from app.scheduler.briefing import build_morning_briefing
from app.scheduler.nudges import build_nudges
from app.scheduler.weekly_digest import build_weekly_digest
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService

logger = logging.getLogger(__name__)


async def send_morning_briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — утренний брифинг не отправлен"
        )
        return

    async with AsyncSessionLocal() as session:
        task_service = TaskService(TaskRepository(session))
        memory_service = MemoryService(MemoryRepository(session))
        habit_service = HabitService(HabitRepository(session))
        goal_service = GoalService(GoalRepository(session))
        text = await build_morning_briefing(
            telegram_user_id,
            task_service,
            memory_service,
            habit_service,
            goal_service,
            ai_client=get_ai_client(settings),
        )

    await context.bot.send_message(chat_id=telegram_user_id, text=text)


_EVENING_REFLECTION_TEXT = (
    "Как прошёл день? 🌙\n"
    "Напишите «дневник: ...» (или «рефлексия: ...», «итоги дня: ...») — "
    "и я запомню."
)


async def send_evening_reflection_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — напоминание о рефлексии не отправлено"
        )
        return

    await context.bot.send_message(
        chat_id=telegram_user_id, text=_EVENING_REFLECTION_TEXT
    )


async def send_proactive_prompt_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Одна проактивная подсказка (см. specs/006-proactive-engagement.md).

    Регистрируется 3 раза (утро/день/вечер, см. app/telegram/bot.py) с
    одним и тем же телом job — вопрос каждый раз выбирается заново.
    Без AI-ключа отвечать на свободный текст всё равно нечем, поэтому в
    этом случае молча ничего не отправляем.
    """
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    ai_client = get_ai_client(settings)
    if ai_client is None:
        return

    async with AsyncSessionLocal() as session:
        service = PendingPromptService(
            PendingPromptRepository(session),
            GoalService(GoalRepository(session)),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        question = await service.pick_and_open(telegram_user_id)

    await context.bot.send_message(chat_id=telegram_user_id, text=question)


async def send_weekly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — еженедельный дайджест не отправлен"
        )
        return

    async with AsyncSessionLocal() as session:
        text = await build_weekly_digest(
            telegram_user_id,
            TaskService(TaskRepository(session)),
            HabitService(HabitRepository(session)),
            GoalService(GoalRepository(session)),
            ai_client=get_ai_client(settings),
        )

    await context.bot.send_message(chat_id=telegram_user_id, text=text)


async def send_nudges_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нэджи по целям/привычкам (см. app/scheduler/nudges.py). Если
    нечего сказать — build_nudges вернёт пустой список и ничего не
    отправляется (как send_task_reminders_job, когда нечего напомнить)."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        lines = await build_nudges(
            telegram_user_id,
            GoalService(GoalRepository(session)),
            HabitService(HabitRepository(session)),
        )

    if not lines:
        return

    await context.bot.send_message(chat_id=telegram_user_id, text="\n\n".join(lines))


async def send_task_reminders_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        task_service = TaskService(TaskRepository(session))
        due_tasks = await task_service.list_due_reminders()
        for task in due_tasks:
            await context.bot.send_message(
                chat_id=telegram_user_id, text=f"⏰ Напоминание: «{task.title}»"
            )
            await task_service.mark_reminded(task.id)
