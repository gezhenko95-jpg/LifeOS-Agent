"""
Извлечение даты из текста на русском языке (без LLM).

Поддерживается:
- относительное время: «через 10 минут», «через 2 часа», «через пару
  часов», «через полчаса», «через час»;
- время суток: «в 18:30», «в 18 30», «в 18.30», «в 18», «в 18 часов»;
- дни: сегодня/завтра/послезавтра, дни недели («в пятницу» — ближайший
  будущий, не сегодняшний), числовые даты dd.mm[.yyyy];
- их сочетание: «завтра в 19:00», «в пятницу в 9».

День и время разбираются раздельно (_extract_day / _extract_clock) и
затем совмещаются в extract_due_date. Дата без времени получает
_DEFAULT_HOUR; время без даты — ближайшее наступление (сегодня, если
ещё не прошло, иначе завтра).
"""

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

_DEFAULT_HOUR = 9

# Все формы слов "минута"/"час" (минута/минуты/минут, час/часа/часов)
# начинаются с одной основы — префиксного матча достаточно, без
# грамматического разбора.
# Количество словами: «через пару часов» — такая же обычная фраза, как
# «через 2 часа», но цифры в ней нет. Список намеренно короткий и
# однозначный: «несколько»/«полтора» разные люди понимают по-разному, а
# ошибка в сроке напоминания дороже, чем непонятая фраза (ADR-004).
_WORD_NUMBERS = {
    "пару": 2,
    "пары": 2,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
}
_COUNT = r"(\d+|" + "|".join(_WORD_NUMBERS) + r")"

_RELATIVE_MINUTES_PATTERN = re.compile(rf"через\s+{_COUNT}\s*минут\w*", re.IGNORECASE)
_RELATIVE_HOURS_PATTERN = re.compile(rf"через\s+{_COUNT}\s*час\w*", re.IGNORECASE)
# «через полчаса» и «через час» — без количества вообще.
_RELATIVE_HALF_HOUR_PATTERN = re.compile(r"через\s+полчаса", re.IGNORECASE)
_RELATIVE_ONE_HOUR_PATTERN = re.compile(r"через\s+час\b", re.IGNORECASE)

# «в 9 утра», «в 7 вечера», «в 3 дня», «в 11 ночи» — 12-часовая форма,
# самая обычная в разговоре. Без неё «в 9 утра» разбиралось как «в 9», а
# слово «утра» оставалось в названии задачи (поймано на живом
# использовании: «напомни сегодня в 9 утра запустить стиралку»).
_DAY_PART_PATTERN = re.compile(
    r"\bв\s+(\d{1,2})(?:[:.\s-](\d{2}))?\s*(утра|дня|вечера|ночи)\b",
    re.IGNORECASE,
)

# Время суток. Разделитель не только двоеточие: «в 19 00», «в 19.00»,
# «в 19-00» пишут ровно так же часто (реальная жалоба владельца).
_TIME_OF_DAY_PATTERN = re.compile(r"\bв\s+(\d{1,2})[:.\s-](\d{2})\b", re.IGNORECASE)
# «в 19», «в 19 часов» — час без минут. Отрицательный просмотр вперёд
# нужен, чтобы не съесть «в 5 минутах ходьбы» и «в 3 дня» как время.
_BARE_HOUR_PATTERN = re.compile(
    r"\bв\s+(\d{1,2})\s*(?:часов|часа|час)?\b"
    r"(?!\s*(?:минут|секунд|дн|недел|мес|год|раз|шт|км|кг))",
    re.IGNORECASE,
)

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
    """Найти дату в тексте, вернуть (дата | None, текст без упоминания даты).

    День и время разбираются РАЗДЕЛЬНО и затем совмещаются: «завтра в
    19:00» это завтра в 19:00, а не «завтра в 09:00» и не «сегодня в
    19:00». Раньше возвращалось первое же совпадение, поэтому у такой
    фразы время выигрывало у дня, дата уезжала на сегодня, а слово
    «завтра» так и оставалось в названии задачи (см. AUDIT.md, B-8).

    «через N часов» разбирается отдельно и раньше всех: это уже полный
    момент времени, совмещать его не с чем.
    """
    due, remaining = _extract_relative_offset(text)
    if due is not None:
        return due, remaining

    day, remaining = _extract_day(text)
    clock, remaining = _extract_clock(remaining)

    if day is not None and clock is not None:
        return datetime.combine(day, clock).astimezone(), remaining
    if day is not None:
        return _at_default_time(day), remaining
    if clock is not None:
        return _next_occurrence_of(clock), remaining
    return None, text


def _extract_day(text: str) -> tuple[Optional[date], str]:
    """Только календарный день, без времени суток."""
    lowered = text.lower()

    if "послезавтра" in lowered:
        return date.today() + timedelta(days=2), _remove_phrase(text, "послезавтра")

    if "завтра" in lowered:
        return date.today() + timedelta(days=1), _remove_phrase(text, "завтра")

    if "сегодня" in lowered:
        return date.today(), _remove_phrase(text, "сегодня")

    weekday_match = _WEEKDAY_PATTERN.search(text)
    if weekday_match:
        word = weekday_match.group(1).lower()
        for prefix, weekday in _WEEKDAYS:
            if word.startswith(prefix):
                days_ahead = (weekday - date.today().weekday()) % 7
                days_ahead = days_ahead or 7  # ближайший будущий, не сегодня
                return (
                    date.today() + timedelta(days=days_ahead),
                    _remove_span(text, weekday_match.span()),
                )

    date_match = _DATE_PATTERN.search(text)
    if date_match:
        day_raw, month_raw, year_raw = date_match.groups()
        parsed_date = _build_date(day_raw, month_raw, year_raw)
        if parsed_date is not None:
            return parsed_date, _remove_span(text, date_match.span())

    return None, text


def _build_date(day_raw: str, month_raw: str, year_raw: str | None) -> Optional[date]:
    """Собрать дату из "дд.мм[.гггг]". None — такой даты не существует.

    Если год НЕ указан явно, а получившаяся дата уже прошла — берём
    следующий год: "встреча 05.01", написанная в декабре, означает
    январь будущего года, а не 11 месяцев назад. Иначе задача создаётся
    сразу просроченной и тут же стреляет напоминанием (см. AUDIT.md, B-7).

    Явно указанный год не трогаем никогда: "01.01.2020" — это осознанно
    прошлое (например, отметить задним числом), догадываться тут не о чем.
    """
    day, month = int(day_raw), int(month_raw)

    if year_raw:
        year = int(year_raw)
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)

    today = date.today()
    parsed = _safe_date(today.year, month, day)
    if parsed is None:
        # 29.02 в невисокосный год — в следующем году может существовать.
        return _safe_date(today.year + 1, month, day)
    if parsed < today:
        # Дата сегодняшняя — оставляем сегодня, а не переносим на год
        # вперёд: "созвон 15.08" утром 15 августа это сегодня.
        return _safe_date(today.year + 1, month, day) or parsed
    return parsed


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


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


def _parse_count(raw: str) -> int:
    """ "2" или "пару" -> 2 (см. _WORD_NUMBERS)."""
    return int(raw) if raw.isdigit() else _WORD_NUMBERS[raw.lower()]


def _extract_relative_offset(text: str) -> tuple[Optional[datetime], str]:
    now = datetime.now().astimezone()

    # «полчаса» раньше «часа»: иначе _RELATIVE_ONE_HOUR_PATTERN не
    # сработает, зато и не должен — «через полчаса» это 30 минут.
    match = _RELATIVE_HALF_HOUR_PATTERN.search(text)
    if match:
        return now + timedelta(minutes=30), _remove_span(text, match.span())

    match = _RELATIVE_MINUTES_PATTERN.search(text)
    if match:
        due = now + timedelta(minutes=_parse_count(match.group(1)))
        return due, _remove_span(text, match.span())

    match = _RELATIVE_HOURS_PATTERN.search(text)
    if match:
        due = now + timedelta(hours=_parse_count(match.group(1)))
        return due, _remove_span(text, match.span())

    match = _RELATIVE_ONE_HOUR_PATTERN.search(text)
    if match:
        return now + timedelta(hours=1), _remove_span(text, match.span())

    return None, text


def _extract_clock(text: str) -> tuple[Optional[time], str]:
    """Только время суток: «в 19:00», «в 19 00», «в 19», «в 19 часов».

    Форма с минутами проверяется первой: у «в 19 00» иначе совпал бы
    только час, а «00» осталось бы в названии задачи.
    """
    match = _DAY_PART_PATTERN.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            hour = _apply_day_part(hour, match.group(3).lower())
            return time(hour=hour, minute=minute), _remove_span(text, match.span())

    match = _TIME_OF_DAY_PATTERN.search(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour=hour, minute=minute), _remove_span(text, match.span())

    match = _BARE_HOUR_PATTERN.search(text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return time(hour=hour), _remove_span(text, match.span())

    return None, text


def _apply_day_part(hour: int, day_part: str) -> int:
    """12-часовой час + часть суток -> час в 24-часовом формате.

    «12 ночи» это полночь, «12 дня» — полдень: двенадцать выбивается из
    общего правила «прибавить 12», поэтому обрабатывается отдельно.
    «11 ночи» — 23:00, а «2 ночи» — 02:00: граница по 4 часам, дальше
    ночь уже переходит в утро.
    """
    if day_part == "утра":
        return 0 if hour == 12 else hour
    if day_part in ("дня", "вечера"):
        return hour if hour == 12 else hour + 12
    # ночи
    if hour == 12:
        return 0
    return hour if hour <= 4 else hour + 12


def _next_occurrence_of(clock: time) -> datetime:
    """Ближайшее наступление этого времени: сегодня, если ещё не прошло,
    иначе завтра — «напомни в 9», написанное вечером, значит завтра утром.

    Применяется, только когда день в тексте НЕ указан: при явном «завтра
    в 9» день берётся из текста, а не угадывается."""
    now = datetime.now().astimezone()
    candidate = now.replace(
        hour=clock.hour, minute=clock.minute, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


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
