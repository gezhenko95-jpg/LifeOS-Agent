"""
Итоги дня для вечернего слота 19:00 (см. flows/009-daily-rhythm.md) —
что сделано сегодня по задачам и привычкам. Отдельно от глубокого
дневникового вопроса 21:00 (app/scheduler/evening_reflection.py).
"""

from datetime import date, datetime, time, timezone

from app.habits.service import HabitService
from app.tasks.service import TaskService


async def build_evening_checkin_text(
    telegram_user_id: int, task_service: TaskService, habit_service: HabitService
) -> str:
    local_tz = datetime.now().astimezone().tzinfo
    today_start = datetime.combine(date.today(), time.min, tzinfo=local_tz).astimezone(
        timezone.utc
    )
    now = datetime.now(timezone.utc)
    completed_today = await task_service.count_tasks_completed_between(
        telegram_user_id, today_start, now
    )

    habits = await habit_service.list_active_habits(telegram_user_id)
    done_today = 0
    for habit in habits:
        completed_days = await habit_service.get_completed_days(habit.id, date.today())
        if date.today() in completed_days:
            done_today += 1

    lines = [
        "Как прошёл день? Итоги:",
        "",
        f"✅ Задач выполнено сегодня: {completed_today}",
    ]
    if habits:
        lines.append(f"🔁 Привычек отмечено: {done_today}/{len(habits)}")
    return "\n".join(lines)
