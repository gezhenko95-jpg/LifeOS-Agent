"""
Извлечение даты из текста на русском языке (без LLM).

Поддерживается: относительное время («через 10 минут», «через 2 часа»),
время суток («в 18:30»), сегодня/завтра/послезавтра, дни недели («в
пятницу» — ближайший будущий день, не сегодняшний), числовые даты
dd.mm[.yyyy].

Упрощение: каждый паттерн проверяется независимо и возвращается первым
совпадением — «завтра в 15:00» распознается только как «завтра» (в
09:00), комбинация день+время не разбирается.
"""

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

_DEFAULT_HOUR = 9

# Все формы слов "минута"/"час" (минута/минуты/минут, час/часа/часов)
# начинаются с одной основы — префиксного матча достаточно, без
# грамматического разбора.
_RELATIVE_MINUTES_PATTERN = re.compile(r"через\s+(\d+)\s*минут\w*", re.IGNORECASE)
_RELATIVE_HOURS_PATTERN = re.compile(r"через\s+(\d+)\s*час\w*", re.IGNORECASE)
_TIME_OF_DAY_PATTERN = re.compile(r"\bв\s+(\d{1,2}):(\d{2})\b", re.IGNORECASE)

_WEEKDAYS: list[tuple[str, int]] = [
    ("понедельник", 0),
    ("вторник", 1),
    ("сред", 2),
    ("четверг", 3),
    ("пятниц", 4),
    ("суббот", 5),
    ("воскресень", 6),
]

_WEEKDAY_PATTERN = re.compile(
    r"\bво?\s+(понедельник|вторник|сред[ауеы]?|четверг|пятниц[ауеы]?"
    r"|суббот[ауеы]?|воскресень[еяию]?)\b",
    re.IGNORECASE,
)

_DATE_PATTERN = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b")

_RECURRENCE_DAILY_PATTERN = re.compile(
    r"\bкаждый\s+день\b|\bежедневно\b", re.IGNORECASE
)
_RECURRENCE_MONTHLY_PATTERN = re.compile(
    r"\bкаждый\s+месяц\b|\bежемесячно\b", re.IGNORECASE
)
_RECURRENCE_WEEKLY_GENERIC_PATTERN = re.compile(
    r"\bкажд\w*\s+недел\w*\b|\bеженедельно\b", re.IGNORECASE
)
_RECURRENCE_WEEKDAY_PATTERN = re.compile(
    r"\bкажд\w*\s+(понедельник|вторник|сред[ауеы]?|четверг|пятниц[ауеы]?"
    r"|суббот[ауеы]?|воскресень[еяию]?)\b",
    re.IGNORECASE,
)


def extract_due_date(text: str) -> tuple[Optional[datetime], str]:
    """Найти дату в тексте, вернуть (дата | None, текст без упоминания даты)."""

    due, remaining = _extract_relative_offset(text)
    if due is not None:
        return due, remaining

    due, remaining = _extract_time_of_day(text)
    if due is not None:
        return due, remaining

    lowered = text.lower()

    if "послезавтра" in lowered:
        due = _at_default_time(date.today() + timedelta(days=2))
        return due, _remove_phrase(text, "послезавтра")

    if "завтра" in lowered:
        due = _at_default_time(date.today() + timedelta(days=1))
        return due, _remove_phrase(text, "завтра")

    if "сегодня" in lowered:
        due = _at_default_time(date.today())
        return due, _remove_phrase(text, "сегодня")

    weekday_match = _WEEKDAY_PATTERN.search(text)
    if weekday_match:
        word = weekday_match.group(1).lower()
        for prefix, weekday in _WEEKDAYS:
            if word.startswith(prefix):
                days_ahead = (weekday - date.today().weekday()) % 7
                days_ahead = days_ahead or 7  # ближайший будущий, не сегодня
                due = _at_default_time(date.today() + timedelta(days=days_ahead))
                return due, _remove_span(text, weekday_match.span())

    date_match = _DATE_PATTERN.search(text)
    if date_match:
        day_raw, month_raw, year_raw = date_match.groups()
        year = date.today().year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        try:
            parsed_date = date(year, int(month_raw), int(day_raw))
        except ValueError:
            return None, text
        return _at_default_time(parsed_date), _remove_span(text, date_match.span())

    return None, text


def extract_recurrence(text: str) -> tuple[Optional[str], str]:
    """Найти признак повторения задачи (см. specs/002-tasks.md, Recurring
    Tasks), вернуть ("daily"|"weekly"|"monthly"|None, остаток текста).

    Для "каждый/каждую <день недели>" (например «каждый понедельник»)
    остаток текста содержит НЕ вырезанную фразу, а подмену на "в <день
    недели>" — чтобы вызывающий код (parser.py), передав остаток в
    extract_due_date следующим шагом, сам нашёл дату этого дня недели
    через уже существующий _WEEKDAY_PATTERN. Так day-of-week логика не
    дублируется.
    """
    match = _RECURRENCE_DAILY_PATTERN.search(text)
    if match:
        return "daily", _remove_span(text, match.span())

    match = _RECURRENCE_MONTHLY_PATTERN.search(text)
    if match:
        return "monthly", _remove_span(text, match.span())

    match = _RECURRENCE_WEEKLY_GENERIC_PATTERN.search(text)
    if match:
        return "weekly", _remove_span(text, match.span())

    match = _RECURRENCE_WEEKDAY_PATTERN.search(text)
    if match:
        weekday_word = match.group(1)
        start, end = match.span()
        replaced = text[:start] + f"в {weekday_word}" + text[end:]
        return "weekly", _clean(replaced)

    return None, text


def _extract_relative_offset(text: str) -> tuple[Optional[datetime], str]:
    match = _RELATIVE_MINUTES_PATTERN.search(text)
    if match:
        due = datetime.now().astimezone() + timedelta(minutes=int(match.group(1)))
        return due, _remove_span(text, match.span())

    match = _RELATIVE_HOURS_PATTERN.search(text)
    if match:
        due = datetime.now().astimezone() + timedelta(hours=int(match.group(1)))
        return due, _remove_span(text, match.span())

    return None, text


def _extract_time_of_day(text: str) -> tuple[Optional[datetime], str]:
    match = _TIME_OF_DAY_PATTERN.search(text)
    if not match:
        return None, text

    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, text

    now = datetime.now().astimezone()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate, _remove_span(text, match.span())


def _at_default_time(day: date) -> datetime:
    return datetime.combine(day, time(hour=_DEFAULT_HOUR)).astimezone()


def _remove_phrase(text: str, phrase: str) -> str:
    pattern = re.compile(re.escape(phrase), re.IGNORECASE)
    return _clean(pattern.sub("", text, count=1))


def _remove_span(text: str, span: tuple[int, int]) -> str:
    start, end = span
    return _clean(text[:start] + text[end:])


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()
