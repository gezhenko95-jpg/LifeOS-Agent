"""
Проактивные нэджи по целям/привычкам (см. flows/008-nudges.md).

Детерминированные условия, без AI (ADR-004) — каждое условие подобрано
так, чтобы срабатывать РОВНО ОДИН раз за жизнь цели/серии, а не спамить
каждый день:
- дедлайн цели: "дней до дедлайна" сравнивается с конкретными порогами
  (3, 1, 0), а не "<=" — при ежедневном запуске джобы попадает под
  условие только один раз на каждый порог;
- обрыв стрика привычки: срабатывает ровно на второй день после
  последней отметки (см. days_since_last_completion) — на следующий день
  условие уже не выполняется.

Если нэджей нет — build_nudges возвращает пустой список, и
send_nudges_job (app/telegram/jobs.py) ничего не отправляет.
"""

from datetime import date

from app.goals.service import GoalService
from app.habits.service import HabitService

_GOAL_DEADLINE_THRESHOLDS = (3, 1, 0)
_STREAK_BREAK_DAYS = 2


async def _goal_deadline_nudges(
    telegram_user_id: int, goal_service: GoalService
) -> list[str]:
    lines = []
    for goal in await goal_service.list_active_goals(telegram_user_id):
        if goal.target_date is None or goal.progress >= 100:
            continue
        days_left = (goal.target_date - date.today()).days
        if days_left not in _GOAL_DEADLINE_THRESHOLDS:
            continue
        when = "сегодня" if days_left == 0 else f"через {days_left} дн."
        lines.append(
            f"⏳ Цель «{goal.title}» — дедлайн {when}, прогресс {goal.progress}%."
        )
    return lines


async def _habit_streak_break_nudges(
    telegram_user_id: int, habit_service: HabitService
) -> list[str]:
    lines = []
    for habit in await habit_service.list_active_habits(telegram_user_id):
        days_since = await habit_service.days_since_last_completion(habit.id)
        if days_since == _STREAK_BREAK_DAYS:
            lines.append(f"💔 Стрик «{habit.title}» прервался — начать заново сегодня?")
    return lines


async def build_nudges(
    telegram_user_id: int, goal_service: GoalService, habit_service: HabitService
) -> list[str]:
    lines: list[str] = []
    lines.extend(await _goal_deadline_nudges(telegram_user_id, goal_service))
    lines.extend(await _habit_streak_break_nudges(telegram_user_id, habit_service))
    return lines
