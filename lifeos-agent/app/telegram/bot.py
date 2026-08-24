"""
Сборка Telegram Application (python-telegram-bot).
"""

import logging
from datetime import datetime, time

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import Settings, get_settings
from app.telegram.callbacks import handle_callback_query
from app.telegram.handlers import (
    digest_add_command,
    digest_list_command,
    digest_new_command,
    digest_now_command,
    digest_remove_command,
    goals_command,
    habits_command,
    handle_photo_message,
    handle_text_message,
    handle_voice_message,
    help_command,
    menu_command,
    start_command,
    tasks_command,
)
from app.telegram.jobs import (
    SUNDAY_WEEKDAY,
    embed_pending_memories_job,
    send_digests_job,
    send_evening_checkin_job,
    send_evening_reflection_job,
    send_finance_report_job,
    send_focus_notifications_job,
    send_habit_reminders_job,
    send_midday_checkin_job,
    send_monthly_insights_job,
    send_morning_briefing_job,
    send_nudges_job,
    send_task_reminders_job,
    send_weekly_digest_job,
)

logger = logging.getLogger(__name__)


def _owner_filter(settings: Settings) -> filters.BaseFilter:
    """Пускать к боту только владельца (проект single-user, PROJECT.md).

    Без этого фильтра посторонний, нашедший бота, тратил деньги владельца
    на OpenRouter, грузил свои фото на ЕГО Google Drive (Media Inbox), а
    его задачи попадали владельцу в чат напоминаниями — джобы намеренно
    не фильтруют по пользователю (см. AUDIT.md, C-4).

    owner_telegram_user_id=0 (ещё не настроен) — фильтр пропускает всех:
    иначе свежепоставленный бот не смог бы ответить на /start, который
    как раз и показывает Telegram ID для настройки.
    """
    if not settings.owner_telegram_user_id:
        return filters.ALL
    return filters.User(user_id=settings.owner_telegram_user_id)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Единая точка для необработанных исключений в хендлерах.

    Без неё падение (например, ValueError на кривом callback_data)
    уходило в лог PTB без контекста, а пользователь не получал ничего и
    видел «бот завис» (см. AUDIT.md, B-3).
    """
    logger.exception("Ошибка при обработке апдейта %s", update, exc_info=context.error)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "telegram_bot_token не задан — заполните .env (см. .env.example)"
        )

    application = Application.builder().token(settings.telegram_bot_token).build()

    owner = _owner_filter(settings)

    application.add_handler(CommandHandler("start", start_command, filters=owner))
    application.add_handler(CommandHandler("help", help_command, filters=owner))
    application.add_handler(CommandHandler("menu", menu_command, filters=owner))
    application.add_handler(CommandHandler("tasks", tasks_command, filters=owner))
    application.add_handler(CommandHandler("habits", habits_command, filters=owner))
    application.add_handler(CommandHandler("goals", goals_command, filters=owner))
    application.add_handler(
        CommandHandler("digest_new", digest_new_command, filters=owner)
    )
    application.add_handler(
        CommandHandler("digest_add", digest_add_command, filters=owner)
    )
    application.add_handler(
        CommandHandler("digest_remove", digest_remove_command, filters=owner)
    )
    application.add_handler(
        CommandHandler("digest_list", digest_list_command, filters=owner)
    )
    application.add_handler(CommandHandler("digest", digest_now_command, filters=owner))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & owner, handle_text_message)
    )
    application.add_handler(MessageHandler(filters.PHOTO & owner, handle_photo_message))
    # Голосовые: хендлер регистрируется, только если фича включена (см.
    # Settings.voice_input_enabled — выключена, пока не решён вопрос с
    # оплатой транскрипции). Незарегистрированный хендлер = бот на
    # голосовое просто молчит; отдельного «фича выключена» не отвечаем,
    # чтобы не анонсировать то, чего сейчас нет.
    if settings.voice_input_enabled:
        application.add_handler(
            MessageHandler(filters.VOICE & owner, handle_voice_message)
        )
    # У CallbackQueryHandler нет параметра filters — проверка владельца
    # живёт внутри самого хендлера (app/telegram/callbacks.py).
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    application.add_error_handler(log_error)

    _register_morning_briefing(application, settings)
    _register_evening_reflection(application, settings)
    _register_task_reminders(application, settings)
    _register_habit_reminders(application, settings)
    _register_focus_notifications(application, settings)
    _register_proactive_prompts(application, settings)
    _register_weekly_digest(application, settings)
    _register_finance_report(application, settings)
    _register_digests(application, settings)
    _register_nudges(application, settings)
    _register_monthly_insights(application, settings)
    _register_memory_embeddings(application, settings)

    return application


def _register_morning_briefing(application: Application, settings: Settings) -> None:
    if not settings.morning_briefing_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_morning_briefing_job,
        time=time(
            hour=settings.morning_briefing_hour,
            minute=settings.morning_briefing_minute,
            tzinfo=local_tz,
        ),
        name="morning_briefing",
    )


def _register_evening_reflection(application: Application, settings: Settings) -> None:
    if not settings.evening_reflection_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_evening_reflection_job,
        time=time(
            hour=settings.evening_reflection_hour,
            minute=settings.evening_reflection_minute,
            tzinfo=local_tz,
        ),
        name="evening_reflection",
    )


def _register_task_reminders(application: Application, settings: Settings) -> None:
    if not settings.task_reminders_enabled or not settings.owner_telegram_user_id:
        return

    application.job_queue.run_repeating(
        send_task_reminders_job,
        interval=settings.task_reminders_interval_seconds,
        first=10,
        name="task_reminders",
    )


def _register_habit_reminders(application: Application, settings: Settings) -> None:
    """Одна джоба на все привычки: время у каждой своё, поэтому она
    крутится с коротким шагом и сама отбирает, кому пора (см.
    HabitService.list_due_reminders) — регистрировать по run_daily на
    каждую привычку значило бы трогать расписание при каждой правке
    времени, тот же довод, что и у дайджестов каналов."""
    if not settings.habit_reminders_enabled or not settings.owner_telegram_user_id:
        return

    application.job_queue.run_repeating(
        send_habit_reminders_job,
        interval=settings.habit_reminders_interval_seconds,
        first=20,
        name="habit_reminders",
    )


def _register_focus_notifications(application: Application, settings: Settings) -> None:
    """Опрос БД на "пора" фокус-сессии (specs/026) — тот же приём и
    довод, что у напоминаний задач/привычек выше."""
    if not settings.focus_notifications_enabled or not settings.owner_telegram_user_id:
        return

    application.job_queue.run_repeating(
        send_focus_notifications_job,
        interval=settings.focus_notifications_interval_seconds,
        first=15,
        name="focus_notifications",
    )


def _register_proactive_prompts(application: Application, settings: Settings) -> None:
    """День/вечер (см. flows/009-daily-rhythm.md) — send_midday_checkin_job,
    send_evening_checkin_job (имена настроек не переименовывали, чтобы не
    задеть уже настроенный .env). Утренний слот (раньше отдельная
    proactive_prompt_morning) с specs/016-engagement-hooks.md слит внутрь
    send_morning_briefing_job — см. _register_morning_briefing."""
    if not settings.proactive_prompts_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_midday_checkin_job,
        time=time(
            hour=settings.proactive_prompt_midday_hour,
            minute=settings.proactive_prompt_midday_minute,
            tzinfo=local_tz,
        ),
        name="proactive_prompt_midday",
    )
    application.job_queue.run_daily(
        send_evening_checkin_job,
        time=time(
            hour=settings.proactive_prompt_evening_hour,
            minute=settings.proactive_prompt_evening_minute,
            tzinfo=local_tz,
        ),
        name="proactive_prompt_evening",
    )


# PTB: 0=понедельник..6=воскресенье, как date.weekday(). Само число
# живёт в jobs.py — им же пользуется send_digests_job для частоты
# "weekly" (см. app/telegram/jobs.py::SUNDAY_WEEKDAY).
_SUNDAY = (SUNDAY_WEEKDAY,)


def _register_weekly_digest(application: Application, settings: Settings) -> None:
    if not settings.weekly_digest_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_weekly_digest_job,
        time=time(
            hour=settings.weekly_digest_hour,
            minute=settings.weekly_digest_minute,
            tzinfo=local_tz,
        ),
        days=_SUNDAY,
        name="weekly_digest",
    )


def _register_finance_report(application: Application, settings: Settings) -> None:
    if not settings.finance_report_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_finance_report_job,
        time=time(
            hour=settings.finance_report_hour,
            minute=settings.finance_report_minute,
            tzinfo=local_tz,
        ),
        days=_SUNDAY,
        name="finance_report",
    )


def _register_digests(application: Application, settings: Settings) -> None:
    """Одна ежедневная job на все дайджесты каналов — «раз в неделю»
    для weekly-дайджестов проверяется внутри send_digests_job (частота
    хранится в данных, а не в расписании, см.
    specs/013-channel-digests.md)."""
    if not settings.digest_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_digests_job,
        time=time(
            hour=settings.digest_hour,
            minute=settings.digest_minute,
            tzinfo=local_tz,
        ),
        name="channel_digests",
    )


def _register_nudges(application: Application, settings: Settings) -> None:
    if not settings.nudges_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_nudges_job,
        time=time(
            hour=settings.nudges_hour, minute=settings.nudges_minute, tzinfo=local_tz
        ),
        name="nudges",
    )


def _register_memory_embeddings(application: Application, settings: Settings) -> None:
    """Доливка embedding для семантического поиска (см.
    specs/011-semantic-memory-search.md) — раз в
    memory_embedding_interval_seconds, сама job тихо пропускает шаг без
    AI-ключа (см. app/telegram/jobs.py::embed_pending_memories_job)."""
    if not settings.memory_embeddings_enabled or not settings.owner_telegram_user_id:
        return

    application.job_queue.run_repeating(
        embed_pending_memories_job,
        interval=settings.memory_embedding_interval_seconds,
        first=30,
        name="memory_embeddings",
    )


def _register_monthly_insights(application: Application, settings: Settings) -> None:
    """Регистрируется как ежедневная job — фильтр "1-е число" внутри
    send_monthly_insights_job (PTB run_daily не умеет "раз в месяц")."""
    if not settings.monthly_insights_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    application.job_queue.run_daily(
        send_monthly_insights_job,
        time=time(
            hour=settings.monthly_insights_hour,
            minute=settings.monthly_insights_minute,
            tzinfo=local_tz,
        ),
        name="monthly_insights",
    )
