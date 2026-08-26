"""
Незапланированные сообщения персонажа (specs/027-butler-personas-phase2.md,
п.2). Решение владельца 26.08: делаем; триггеры — стрик привычки
оборвался ИЛИ задача давно просрочена без движения; частота — не чаще
2 раз в день (владелец прямо попросил цель «побуждать заходить»
дважды в день).

Не отдельная джоба/расписание — довесок к двум уже существующим дневным
слотам (`send_midday_checkin_job` 14:00, `send_evening_checkin_job`
19:00, см. `app/telegram/jobs.py`), тот же приём, что уже был у
Engagement Hooks («утренняя рефлексия слита в send_morning_briefing_job»,
см. HANDOFF, архив 23.08 ночь #3) — не плодить новые cron-времена ради
небольшого довеска к уже существующему сообщению. Ровно два слота в
день — из этого следует лимит "не чаще 2 раз в день" сам по себе, без
отдельного счётчика.

Дедуп в рамках дня (одна и та же причина не должна прийти на ОБОИХ
сегодняшних слотах — условие day_since==N не меняется в течение дня) —
на стороне вызывающего кода (AssistantService.was_nudge_already_sent_today/
record_nudge_sent), этот модуль только читает и ничего не пишет
(тот же принцип, что у app/scheduler/nudges.py — чистая функция).
"""

import logging
from datetime import datetime, timezone

from app.ai.client import AIClient, AIServiceError
from app.assistant.personas import Persona, build_insight_prompt
from app.habits.service import HabitService
from app.tasks.service import TaskService

logger = logging.getLogger(__name__)

_NUDGE_TASK_INSTRUCTION = (
    "Замечена такая ситуация у пользователя: {situation} Незапрошенно, "
    "по своей инициативе, коротко обратись к нему в своём характере — "
    "1-2 предложения (примерно до 40 слов), мягко обрати внимание и "
    "мотивируй заглянуть в приложение/бот, без давления и морализаторства. "
    "На русском языке, без предисловий, без кавычек и markdown. Верни "
    "только текст сообщения, ничего больше."
)

# Тот же порог, что у app/scheduler/nudges.py::_STREAK_BREAK_DAYS —
# срабатывает ровно на второй день после последней отметки, не долбит
# каждый день подряд.
_STREAK_BREAK_DAYS = 2
# Задача просрочена ровно N дней (day-threshold, не "<=") — тот же
# приём, чтобы условие выполнялось один раз на конкретную задачу, а не
# на каждом опросе, пока она остаётся незавершённой.
_OVERDUE_TASK_DAYS = 3


async def find_nudge_candidate(
    telegram_user_id: int,
    habit_service: HabitService,
    task_service: TaskService,
    exclude_trigger_key: str | None = None,
) -> tuple[str, str] | None:
    """Первый подходящий триггер: (ключ для дедупа, описание ситуации
    для AI-промпта). `exclude_trigger_key` — уже использованный сегодня
    на предыдущем слоте триггер пропускается, чтобы второй слот дня мог
    найти ДРУГОЙ повод, а не просто заново упереться в тот же и молчать.
    None, если сегодня подходящих поводов больше нет."""
    habits = await habit_service.list_active_habits(telegram_user_id)
    if habits:
        days_since_by_habit = await habit_service.days_since_last_completion_bulk(
            telegram_user_id, [h.id for h in habits]
        )
        for habit in habits:
            if days_since_by_habit.get(habit.id) != _STREAK_BREAK_DAYS:
                continue
            key = f"habit_streak:{habit.id}"
            if key == exclude_trigger_key:
                continue
            return (
                key,
                f"Стрик привычки «{habit.title}» прервался "
                f"{_STREAK_BREAK_DAYS} дня назад, пользователь ещё не "
                "начал заново.",
            )

    now = datetime.now(timezone.utc)
    for task in await task_service.list_active_tasks(telegram_user_id):
        if task.due_date is None:
            continue
        due = (
            task.due_date
            if task.due_date.tzinfo
            else task.due_date.replace(tzinfo=timezone.utc)
        )
        if (now - due).days != _OVERDUE_TASK_DAYS:
            continue
        key = f"task_overdue:{task.id}"
        if key == exclude_trigger_key:
            continue
        return (
            key,
            f"Задача «{task.title}» просрочена уже {_OVERDUE_TASK_DAYS} "
            "дня и всё ещё не завершена.",
        )

    return None


async def generate_nudge_text(
    ai_client: AIClient, situation: str, persona: Persona
) -> str | None:
    """AI-фраза в голосе персонажа под конкретную ситуацию — тот же
    паттерн, что build_finance_report/_generate_insight
    (app/scheduler/finance_report.py): тихий None на ошибке AI, не
    падение. Без AI фичи вообще не бывает (см. вызывающий код в
    jobs.py) — детерминированного шаблона без AI сознательно нет,
    иначе одно и то же сообщение приедалось бы уже через пару недель."""
    instruction = _NUDGE_TASK_INSTRUCTION.format(situation=situation)
    messages = [
        {"role": "system", "content": build_insight_prompt(persona, instruction)},
        {"role": "user", "content": situation},
    ]
    try:
        text = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI не сгенерировал незапланированное сообщение: %s", exc)
        return None

    text = text.strip()
    return text or None
