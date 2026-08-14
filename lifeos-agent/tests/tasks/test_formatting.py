"""
Показ сроков задач (см. app/tasks/formatting.py).
"""

from datetime import date, datetime, timedelta, timezone

from app.tasks.formatting import (
    format_due_date,
    format_due_human,
    task_status_emoji,
)
from app.tasks.models import Task


def _task(due_date=None, priority="normal") -> Task:
    return Task(
        id=1,
        telegram_user_id=1,
        title="Задача",
        due_date=due_date,
        status="active",
        priority=priority,
    )


def test_utc_from_db_is_shown_in_local_time():
    """asyncpg возвращает timestamptz в UTC. Без перевода «напомни в 9
    утра» отвечало «в 06:00»: задача создавалась верно, врал только
    текст — пользователь видел чужое время и переставал верить боту."""
    utc_dt = datetime(2026, 8, 16, 19, 0, tzinfo=timezone.utc)
    local = utc_dt.astimezone()

    assert format_due_date(utc_dt) == f"{local:%d.%m.%Y} в {local:%H:%M}"

    if local.utcoffset() != timedelta(0):
        # На машине не в UTC результат обязан отличаться от «сырых» 19:00,
        # иначе перевод не произошёл.
        assert format_due_date(utc_dt) != "16.08.2026 в 19:00"


def test_naive_datetime_is_left_alone():
    """astimezone() на наивной дате молча приписал бы ей локальную зону."""
    assert format_due_date(datetime(2026, 8, 16, 19, 0)) == "16.08.2026 в 19:00"


def test_human_dates_use_words_for_near_days():
    today = date(2026, 8, 15)

    assert format_due_human(datetime(2026, 8, 15, 19, 0), today) == "сегодня в 19:00"
    assert format_due_human(datetime(2026, 8, 16, 9, 0), today) == "завтра в 09:00"
    assert format_due_human(datetime(2026, 8, 14, 9, 0), today) == "вчера в 09:00"


def test_human_dates_fall_back_to_numbers_when_far():
    today = date(2026, 8, 15)

    assert format_due_human(datetime(2026, 8, 30, 9, 0), today) == "вс, 30.08 в 09:00"


def test_overdue_is_marked_explicitly():
    today = date(2026, 8, 15)

    assert "просрочено" in format_due_human(datetime(2026, 8, 10, 9, 0), today)


def test_status_emoji_by_urgency():
    today = date(2026, 8, 15)

    assert task_status_emoji(_task(datetime(2026, 8, 10, 9, 0)), today) == "🔴"
    assert task_status_emoji(_task(datetime(2026, 8, 15, 9, 0)), today) == "🟠"
    assert task_status_emoji(_task(datetime(2026, 8, 16, 9, 0)), today) == "🟡"
    assert task_status_emoji(_task(datetime(2026, 8, 20, 9, 0)), today) == "⚪"
    assert task_status_emoji(_task(None), today) == "⚪"
