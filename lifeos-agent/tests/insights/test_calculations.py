"""
Чистые функции находок Personal Insights (см. specs/009-personal-insights.md).
Без БД, без моков — на входе данные, на выходе фраза или None.
"""

from datetime import date, datetime, timedelta, timezone

from app.insights.calculations import (
    deadline_discipline,
    journal_habit_correlation,
    longest_streak_finding,
    productive_weekday,
)

# --- productive_weekday -------------------------------------------------


def _dt_on_weekday(weekday: int, week_offset: int = 0) -> datetime:
    """Понедельник (weekday=0) недели `week_offset` относительно якоря +
    смещение до нужного дня недели."""
    anchor = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)  # понедельник
    return anchor + timedelta(weeks=week_offset, days=weekday)


def test_productive_weekday_empty_returns_none():
    assert productive_weekday([]) is None


def test_productive_weekday_below_threshold_returns_none():
    completed = [_dt_on_weekday(1, i) for i in range(9)]  # 9 < порога 10

    assert productive_weekday(completed) is None


def test_productive_weekday_clear_skew():
    # 10 задач по вторникам (weekday=1), 2 по субботе (weekday=5).
    completed = [_dt_on_weekday(1, i) for i in range(10)] + [
        _dt_on_weekday(5, i) for i in range(2)
    ]

    result = productive_weekday(completed)

    assert result is not None
    assert "вторникам" in result
    assert "субботам" in result


def test_productive_weekday_uniform_distribution_does_not_crash():
    completed = [_dt_on_weekday(day % 7, day) for day in range(14)]

    result = productive_weekday(completed)

    assert isinstance(result, str)


def test_productive_weekday_all_same_day():
    completed = [_dt_on_weekday(2, i) for i in range(10)]

    result = productive_weekday(completed)

    assert result == "Все задачи в этом окне закрыты по средам."


# --- journal_habit_correlation ------------------------------------------


def _days(count: int, start: date = date(2026, 6, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def test_journal_habit_correlation_no_habits_returns_none():
    result = journal_habit_correlation(_days(10), set(), {}, total_habits=0)

    assert result is None


def test_journal_habit_correlation_too_few_days_returns_none():
    window = _days(10)
    journal_dates = set(window[:3])  # только 3 дня с дневником — меньше порога 5

    result = journal_habit_correlation(window, journal_dates, {}, total_habits=1)

    assert result is None


def test_journal_habit_correlation_clear_signal():
    window = _days(20)
    journal_dates = set(window[:10])
    no_journal_days = window[10:]
    # В дни с дневником привычка выполнена всегда (100%), без — только в
    # 2 из 10 дней (20%) — явный, но не нулевой контраст.
    habit_completion_counts = {day: 1 for day in journal_dates}
    habit_completion_counts.update({day: 1 for day in no_journal_days[:2]})

    result = journal_habit_correlation(
        window, journal_dates, habit_completion_counts, total_habits=1
    )

    assert result is not None
    assert "100%" in result
    assert "20%" in result
    assert "5.0 раза" in result


def test_journal_habit_correlation_zero_baseline_returns_none_without_crashing():
    window = _days(20)
    journal_dates = set(window[:10])
    # Ни одного выполнения ни в дни с дневником, ни без — делить не на что.
    result = journal_habit_correlation(window, journal_dates, {}, total_habits=1)

    assert result is None


# --- deadline_discipline --------------------------------------------------


def _pair(
    due_offset_days: int, completed_offset_days: int
) -> tuple[datetime, datetime]:
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return (
        base + timedelta(days=due_offset_days),
        base + timedelta(days=completed_offset_days),
    )


def test_deadline_discipline_below_threshold_returns_none():
    pairs = [_pair(0, 0) for _ in range(4)]

    assert deadline_discipline(pairs) is None


def test_deadline_discipline_all_on_time():
    pairs = [_pair(5, 4) for _ in range(5)]

    result = deadline_discipline(pairs)

    assert (
        result
        == "0 из 5 задач со сроком в этом окне закрыты позже дедлайна — всё вовремя."
    )


def test_deadline_discipline_mixed_case():
    pairs = [_pair(0, 0) for _ in range(3)] + [_pair(0, 2) for _ in range(2)]

    result = deadline_discipline(pairs)

    assert "2 из 5 задач" in result
    assert "2 дня" in result


# --- longest_streak_finding -----------------------------------------------


def test_longest_streak_finding_empty_returns_none():
    assert longest_streak_finding({}) is None


def test_longest_streak_finding_all_zero_returns_none():
    assert longest_streak_finding({"Чтение": 0}) is None


def test_longest_streak_finding_picks_max():
    result = longest_streak_finding({"Чтение": 3, "Спорт": 14})

    assert result == "Рекорд серии — «Спорт», 14 дней подряд."
