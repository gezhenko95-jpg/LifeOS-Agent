"""
Проактивные нэджи по целям/привычкам/контактам (см. flows/008-nudges.md,
specs/018-personal-crm.md).

Детерминированные условия, без AI (ADR-004) — каждое условие подобрано
так, чтобы срабатывать РОВНО ОДИН раз за жизнь цели/серии/контакта, а не
спамить каждый день:
- дедлайн цели: "дней до дедлайна" сравнивается с конкретными порогами
  (3, 1, 0), а не "<=" — при ежедневном запуске джобы попадает под
  условие только один раз на каждый порог;
- обрыв стрика привычки: срабатывает ровно на второй день после
  последней отметки (см. days_since_last_completion) — на следующий день
  условие уже не выполняется;
- контакт "давно не писал" — та же схема, что у стрика: ровно на 30-й
  день с последнего контакта;
- день рождения — та же схема порогов, что у дедлайна цели (3, 1, 0).

Если нэджей нет — build_nudges возвращает пустой список, и
send_nudges_job (app/telegram/jobs.py) ничего не отправляет.
"""

from datetime import date, datetime, timezone

from app.crm.service import ContactService
from app.goals.service import GoalService
from app.habits.service import HabitService

_GOAL_DEADLINE_THRESHOLDS = (3, 1, 0)
_STREAK_BREAK_DAYS = 2
_BIRTHDAY_THRESHOLDS = (3, 1, 0)
_STALE_CONTACT_DAYS = 30


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
    habits = await habit_service.list_active_habits(telegram_user_id)
    days_since_by_habit = await habit_service.days_since_last_completion_bulk(
        telegram_user_id, [h.id for h in habits]
    )
    lines = []
    for habit in habits:
        if days_since_by_habit.get(habit.id) == _STREAK_BREAK_DAYS:
            lines.append(f"💔 Стрик «{habit.title}» прервался — начать заново сегодня?")
    return lines


def _date_or_shifted(year: int, month: int, day: int) -> date:
    """(month, day) валидны в любом високосном году (проверено при
    создании контакта, см. app/crm/service.py::_validate_birthday) —
    единственный случай, когда date(year, month, day) не существует для
    конкретного year, это 29 февраля в невисокосный год. Сдвигаем на
    1 марта (вперёд, не на 28 февраля назад) — тот же принцип, что и у
    остальных таких сдвигов дат в проекте."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 3, 1)


def _next_occurrence(month: int, day: int, today: date) -> date:
    """Ближайшее будущее (или сегодняшнее) вхождение (month, day) от today."""
    candidate = _date_or_shifted(today.year, month, day)
    if candidate >= today:
        return candidate
    return _date_or_shifted(today.year + 1, month, day)


async def _upcoming_birthday_nudges(
    telegram_user_id: int, contact_service: ContactService
) -> list[str]:
    today = date.today()
    lines = []
    for contact in await contact_service.list_contacts(telegram_user_id):
        if contact.birthday_month is None or contact.birthday_day is None:
            continue
        occurrence = _next_occurrence(
            contact.birthday_month, contact.birthday_day, today
        )
        days_left = (occurrence - today).days
        if days_left not in _BIRTHDAY_THRESHOLDS:
            continue
        when = "сегодня" if days_left == 0 else f"через {days_left} дн."
        lines.append(f"🎂 День рождения «{contact.name}» — {when}.")
    return lines


async def _stale_contact_nudges(
    telegram_user_id: int, contact_service: ContactService
) -> list[str]:
    now = datetime.now(timezone.utc)
    lines = []
    for contact in await contact_service.list_contacts(telegram_user_id):
        last_contact_at = contact.last_contact_at
        if last_contact_at.tzinfo is None:
            last_contact_at = last_contact_at.replace(tzinfo=timezone.utc)
        days_since = (now - last_contact_at).days
        if days_since == _STALE_CONTACT_DAYS:
            lines.append(f"👋 Давно не писал(а) «{contact.name}» — {days_since} дней.")
    return lines


async def build_nudges(
    telegram_user_id: int,
    goal_service: GoalService,
    habit_service: HabitService,
    contact_service: ContactService | None = None,
) -> list[str]:
    """`contact_service=None` тихо отключает CRM-нэджи — тот же паттерн
    опциональности, что у ConversationEngine (см. app/conversation/
    engine.py)."""
    lines: list[str] = []
    lines.extend(await _goal_deadline_nudges(telegram_user_id, goal_service))
    lines.extend(await _habit_streak_break_nudges(telegram_user_id, habit_service))
    if contact_service is not None:
        lines.extend(await _upcoming_birthday_nudges(telegram_user_id, contact_service))
        lines.extend(await _stale_contact_nudges(telegram_user_id, contact_service))
    return lines
