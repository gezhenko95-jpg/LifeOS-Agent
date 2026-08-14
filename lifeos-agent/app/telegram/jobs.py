"""
Фоновые задачи Telegram-бота (Scheduler), см. flows/001-morning-briefing.md.
"""

import logging
import random
from datetime import date

from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.insights.formatting import build_insights_text
from app.insights.service import InsightsService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.proactive.repository import PendingPromptRepository
from app.proactive.service import PendingPromptService
from app.scheduler.briefing import build_morning_briefing
from app.scheduler.charts import gather_chart_data, render_chart
from app.scheduler.evening_checkin import build_evening_checkin_text
from app.scheduler.evening_reflection import build_evening_reflection_prompt
from app.scheduler.nudges import build_nudges
from app.scheduler.weekly_digest import build_weekly_digest
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
from app.telegram.keyboards import build_habits_message

logger = logging.getLogger(__name__)

# Лимит Telegram на подпись к фото — если текст дайджеста вдруг длиннее,
# шлём фото без подписи и текст отдельным сообщением, а не падаем на API.
_PHOTO_CAPTION_LIMIT = 1024

_MIDDAY_TEXT = "Как проходит твой день? 🌤 Отметь, что уже успел:"
_MIDDAY_TEXT_NO_HABITS = "Как проходит твой день? 🌤"

# Вечерний итоговый слот 19:00: доля сообщений, к которым снизу
# добавляется gap-вопрос про профиль (только если гэп реально есть).
_EVENING_GAP_CHANCE = 0.5


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
        chart = await _try_build_chart(telegram_user_id, task_service, habit_service)

    await _send_text_or_photo(context, telegram_user_id, text, chart)


async def send_evening_reflection_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вечерний слот 21:00 (см. flows/009-daily-rhythm.md) — глубокий
    AI-вопрос для дневника (заменяет прежний статичный текст с просьбой
    напечатать "дневник: ..."). Открывает category="journal" — ответ
    ловится ConversationEngine._try_capture_journal без префикса."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — вечерняя рефлексия не отправлена"
        )
        return

    async with AsyncSessionLocal() as session:
        question = await build_evening_reflection_prompt(get_ai_client(settings))
        await PendingPromptRepository(session).upsert(
            telegram_user_id, "journal", question
        )

    await context.bot.send_message(chat_id=telegram_user_id, text=question)


async def send_morning_reflection_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Утренний рефлексивный слот 10:30 (см. flows/009-daily-rhythm.md) —
    сон, факт/экзистенциальный вопрос, или (если есть реальный гэп в
    профиле) обычный проактивный вопрос про цель/привычку/проект.

    Дневниковая ветка (сон) не зависит от AI-ключа (нечего разбирать) и
    работает всегда; gap-ветка (вопрос про цель/привычку/проект) требует
    AI для разбора ответа (ConversationEngine._try_answer_pending_prompt)
    — без ключа передаём allow_gap=False, чтобы не открывать вопрос, на
    который бот сам же не сможет распознать ответ.
    """
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        service = PendingPromptService(
            PendingPromptRepository(session),
            GoalService(GoalRepository(session)),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        question = await service.pick_morning_reflection(
            telegram_user_id, allow_gap=ai_client is not None
        )

    await context.bot.send_message(chat_id=telegram_user_id, text=question)


async def send_midday_checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Дневной слот 14:00 (см. flows/009-daily-rhythm.md) — «как дела» +
    табличка привычек прямо под сообщением (переиспользует
    build_habits_message — то же, что и по команде /habits), чтобы
    отметить выполненное можно было в один тап, без печати."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        habit_service = HabitService(HabitRepository(session))
        habits = await habit_service.list_active_habits(telegram_user_id)
        if not habits:
            await context.bot.send_message(
                chat_id=telegram_user_id, text=_MIDDAY_TEXT_NO_HABITS
            )
            return
        streaks = {h.id: await habit_service.get_streak(h.id) for h in habits}
        _, markup = build_habits_message(habits, streaks)

    await context.bot.send_message(
        chat_id=telegram_user_id, text=_MIDDAY_TEXT, reply_markup=markup
    )


async def send_evening_checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вечерний итоговый слот 19:00 (см. flows/009-daily-rhythm.md) —
    что сделано сегодня (задачи/привычки) + иногда, если есть реальный
    гэп в профиле, gap-вопрос про цель/привычку/проект снизу. Вопрос —
    необязательное дополнение здесь, не главное содержание сообщения."""
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    ai_client = get_ai_client(settings)

    async with AsyncSessionLocal() as session:
        task_service = TaskService(TaskRepository(session))
        habit_service = HabitService(HabitRepository(session))
        text = await build_evening_checkin_text(
            telegram_user_id, task_service, habit_service
        )

        if ai_client is not None and random.random() < _EVENING_GAP_CHANCE:
            service = PendingPromptService(
                PendingPromptRepository(session),
                GoalService(GoalRepository(session)),
                habit_service,
                MemoryService(MemoryRepository(session)),
            )
            gap_question = await service.pick_gap_question_if_any(telegram_user_id)
            if gap_question:
                text = f"{text}\n\n{gap_question}"

    await context.bot.send_message(chat_id=telegram_user_id, text=text)


async def send_weekly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        logger.warning(
            "owner_telegram_user_id не задан — еженедельный дайджест не отправлен"
        )
        return

    async with AsyncSessionLocal() as session:
        task_service = TaskService(TaskRepository(session))
        habit_service = HabitService(HabitRepository(session))
        text = await build_weekly_digest(
            telegram_user_id,
            task_service,
            habit_service,
            GoalService(GoalRepository(session)),
            ai_client=get_ai_client(settings),
        )
        chart = await _try_build_chart(telegram_user_id, task_service, habit_service)

    await _send_text_or_photo(context, telegram_user_id, text, chart)


async def _try_build_chart(
    telegram_user_id: int, task_service: TaskService, habit_service: HabitService
):
    """Картинка — бонус, а не критичная часть сообщения; сбой рендера
    (например, из-за шрифтов) не должен срывать отправку текста (тот же
    принцип, что и у AI-инсайтов везде в проекте)."""
    try:
        chart_data = await gather_chart_data(
            telegram_user_id, task_service, habit_service
        )
        return render_chart(chart_data)
    except Exception:
        logger.exception("Не удалось построить график")
        return None


async def _send_text_or_photo(
    context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int, text: str, chart
) -> None:
    if chart is None:
        await context.bot.send_message(chat_id=telegram_user_id, text=text)
        return

    if len(text) <= _PHOTO_CAPTION_LIMIT:
        await context.bot.send_photo(
            chat_id=telegram_user_id, photo=chart, caption=text
        )
    else:
        await context.bot.send_photo(chat_id=telegram_user_id, photo=chart)
        await context.bot.send_message(chat_id=telegram_user_id, text=text)


async def send_monthly_insights_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Personal Insights раз в месяц, 1-е число (см.
    specs/009-personal-insights.md, flows/010-personal-insights.md).
    PTB JobQueue не умеет "раз в месяц" из коробки — регистрируется как
    ежедневная job (см. app/telegram/bot.py), а фильтр по дню — здесь.
    Тихий пропуск, если находок нет — фоновая рассылка не должна слать
    "недостаточно данных", это шум (в отличие от кнопки "📊 Инсайты" по
    запросу, см. app/telegram/handlers.py::_send_insights)."""
    if date.today().day != 1:
        return

    settings = get_settings()
    telegram_user_id = settings.owner_telegram_user_id
    if not telegram_user_id:
        return

    async with AsyncSessionLocal() as session:
        service = InsightsService(
            TaskService(TaskRepository(session)),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        findings = await service.build_findings(telegram_user_id)

    if not findings:
        return

    await context.bot.send_message(
        chat_id=telegram_user_id, text=build_insights_text(findings)
    )


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
