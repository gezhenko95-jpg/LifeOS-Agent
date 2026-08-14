"""
Чистые функции для находок Personal Insights (см.
specs/009-personal-insights.md). Без обращений к БД — принимают уже
выбранные данные, возвращают готовую фразу или None, если данных
недостаточно, чтобы находка что-то значила (пороги — см. спеку).
Тестируются без моков (по образцу app/scheduler/charts.py:
gather_chart_data/render_chart).
"""

from collections import Counter
from datetime import date, datetime
from statistics import mean

_MIN_TASKS_FOR_WEEKDAY = 10
_MIN_DAYS_PER_GROUP = 5
_MIN_DEADLINE_TASKS = 5

_WEEKDAY_DATIVE_PLURAL = {
    0: "понедельникам",
    1: "вторникам",
    2: "средам",
    3: "четвергам",
    4: "пятницам",
    5: "субботам",
    6: "воскресеньям",
}


def _pluralize(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _pluralize_days(count: int) -> str:
    return _pluralize(count, "день", "дня", "дней")


def productive_weekday(completed_at: list[datetime]) -> str | None:
    """Находка 1: самый (и, если есть разброс, наименее) продуктивный
    день недели по Task.completed_at. None, если задач меньше порога —
    на маленькой выборке день недели ничего не значит."""
    if len(completed_at) < _MIN_TASKS_FOR_WEEKDAY:
        return None

    counts = Counter(dt.weekday() for dt in completed_at)
    total = len(completed_at)
    best_day, best_count = counts.most_common(1)[0]
    best_pct = round(best_count / total * 100)
    best_name = _WEEKDAY_DATIVE_PLURAL[best_day]

    if len(counts) == 1:
        return f"Все задачи в этом окне закрыты по {best_name}."

    worst_day, worst_count = min(counts.items(), key=lambda kv: kv[1])
    worst_pct = round(worst_count / total * 100)
    worst_name = _WEEKDAY_DATIVE_PLURAL[worst_day]

    return (
        f"Чаще всего задачи закрываются по {best_name} ({best_pct}%), "
        f"реже всего — по {worst_name} ({worst_pct}%)."
    )


def journal_habit_correlation(
    window_days: list[date],
    journal_dates: set[date],
    habit_completion_counts: dict[date, int],
    total_habits: int,
) -> str | None:
    """Находка 2: доля выполненных привычек в дни с дневниковой записью
    против дней без неё. None, если нет привычек, если дней одного из
    типов меньше порога, или если в дни без дневника ничего не
    выполнялось (множитель был бы бесконечным — не роняем функцию, а
    просто не показываем находку, см. specs/009-personal-insights.md)."""
    if total_habits <= 0:
        return None

    journal_rates = []
    no_journal_rates = []
    for day in window_days:
        rate = habit_completion_counts.get(day, 0) / total_habits
        (journal_rates if day in journal_dates else no_journal_rates).append(rate)

    if (
        len(journal_rates) < _MIN_DAYS_PER_GROUP
        or len(no_journal_rates) < _MIN_DAYS_PER_GROUP
    ):
        return None

    avg_journal = mean(journal_rates)
    avg_no_journal = mean(no_journal_rates)
    if avg_no_journal <= 0:
        return None

    multiplier = avg_journal / avg_no_journal
    return (
        f"В дни, когда ты пишешь дневник, привычки выполняются в "
        f"{multiplier:.1f} раза чаще ({round(avg_journal * 100)}% против "
        f"{round(avg_no_journal * 100)}%)."
    )


def deadline_discipline(pairs: list[tuple[datetime, datetime]]) -> str | None:
    """Находка 3: доля просроченных завершённых задач + средняя
    задержка. `pairs` — (due_date, completed_at), только завершённые
    задачи со сроком. None, если таких задач меньше порога."""
    total = len(pairs)
    if total < _MIN_DEADLINE_TASKS:
        return None

    late_delays_days = [
        (completed - due).total_seconds() / 86400
        for due, completed in pairs
        if completed > due
    ]
    late_count = len(late_delays_days)
    if late_count == 0:
        return (
            f"0 из {total} задач со сроком в этом окне закрыты позже "
            "дедлайна — всё вовремя."
        )

    avg_delay = mean(late_delays_days)
    delay_days = round(avg_delay)
    delay_phrase = (
        "в среднем меньше чем на день"
        if delay_days == 0
        else f"в среднем на {delay_days} {_pluralize_days(delay_days)}"
    )
    return (
        f"{late_count} из {total} задач со сроком в этом окне "
        f"закрыты позже дедлайна, {delay_phrase}."
    )


def longest_streak_finding(streaks: dict[str, int]) -> str | None:
    """Находка 4: рекорд самой длинной серии среди всех привычек. None,
    если привычек нет или ни одна ни разу не отмечалась."""
    if not streaks:
        return None

    best_title, best_value = max(streaks.items(), key=lambda kv: kv[1])
    if best_value <= 0:
        return None

    return (
        f"Рекорд серии — «{best_title}», {best_value} "
        f"{_pluralize_days(best_value)} подряд."
    )
