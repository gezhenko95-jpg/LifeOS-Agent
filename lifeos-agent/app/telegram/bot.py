"""
Сборка Telegram Application (python-telegram-bot).
"""

from datetime import datetime, time

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.core.config import Settings, get_settings
from app.telegram.callbacks import handle_callback_query
from app.telegram.handlers import (
    goals_command,
    habits_command,
    handle_text_message,
    help_command,
    start_command,
    tasks_command,
)
from app.telegram.jobs import (
    send_evening_reflection_job,
    send_morning_briefing_job,
    send_nudges_job,
    send_proactive_prompt_job,
    send_task_reminders_job,
    send_weekly_digest_job,
)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "telegram_bot_token не задан — заполните .env (см. .env.example)"
        )

    application = Application.builder().token(settings.telegram_bot_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("habits", habits_command))
    application.add_handler(CommandHandler("goals", goals_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    _register_morning_briefing(application, settings)
    _register_evening_reflection(application, settings)
    _register_task_reminders(application, settings)
    _register_proactive_prompts(application, settings)
    _register_weekly_digest(application, settings)
    _register_nudges(application, settings)

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


def _register_proactive_prompts(application: Application, settings: Settings) -> None:
    if not settings.proactive_prompts_enabled or not settings.owner_telegram_user_id:
        return

    local_tz = datetime.now().astimezone().tzinfo
    slots = (
        (
            "proactive_prompt_morning",
            settings.proactive_prompt_morning_hour,
            settings.proactive_prompt_morning_minute,
        ),
        (
            "proactive_prompt_midday",
            settings.proactive_prompt_midday_hour,
            settings.proactive_prompt_midday_minute,
        ),
        (
            "proactive_prompt_evening",
            settings.proactive_prompt_evening_hour,
            settings.proactive_prompt_evening_minute,
        ),
    )
    for name, hour, minute in slots:
        application.job_queue.run_daily(
            send_proactive_prompt_job,
            time=time(hour=hour, minute=minute, tzinfo=local_tz),
            name=name,
        )


_SUNDAY = (6,)  # PTB: 0=понедельник..6=воскресенье, как date.weekday()


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
