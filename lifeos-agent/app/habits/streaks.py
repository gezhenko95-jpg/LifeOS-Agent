"""
Чистые функции расчёта стрика по уже загруженным логам (без БД).

Раньше вся эта логика жила в HabitService и разбирала список HabitLog по
одной привычке за раз, вызванный из HabitRepository.list_logs. Любой
экран, показывающий стрики нескольким привычкам сразу (список привычек,
брифинг, дайджест, инсайты), делал по запросу на КАЖДУЮ привычку в цикле
— классический N+1 (см. AUDIT.md, P-1). Здесь функции принимают уже
сгруппированные дни на входе, поэтому пригодны и для одиночного, и для
пакетного пути (см. HabitRepository.list_logs_for_habits).
"""

from datetime import date, timedelta


def current_streak(completed_days: set[date], today: date | None = None) -> int:
    """Сколько дней подряд выполнялась привычка, включая сегодня.

    Если сегодня ещё не отмечено — стрик считается с вчерашнего дня,
    чтобы серия не обрывалась только потому, что день не закончился.
    """
    if not completed_days:
        return 0

    today = today or date.today()
    cursor = today
    if cursor not in completed_days:
        cursor -= timedelta(days=1)

    streak = 0
    while cursor in completed_days:
        streak += 1
        cursor -= timedelta(days=1)

    return streak


def longest_streak(completed_days: set[date]) -> int:
    """Рекорд самой длинной последовательности подряд идущих дней — не
    обязательно текущей, а за всю историю."""
    if not completed_days:
        return 0

    ordered = sorted(completed_days)
    longest = 1
    current = 1
    for previous_day, day in zip(ordered, ordered[1:], strict=False):
        current = current + 1 if day == previous_day + timedelta(days=1) else 1
        longest = max(longest, current)
    return longest


def days_since_last(completed_days: set[date], today: date | None = None) -> int | None:
    """None — ни разу не отмечалась."""
    if not completed_days:
        return None
    today = today or date.today()
    return (today - max(completed_days)).days
