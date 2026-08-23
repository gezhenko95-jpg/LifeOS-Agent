"""
Извлечение дня рождения (месяц + день, без года) из текста на русском
языке (без LLM) — для ответа на кнопку «➕ Добавить» в разделе «📇 Люди»
(см. specs/018-personal-crm.md).

Контракт — как у amount_parser.py::extract_amount: (месяц, день) или
(None, None), плюс остаток текста без найденного фрагмента. Год
намеренно не разбирается, даже если написан («14.09.1990») — фича не
про возраст, только про повторяющуюся дату, см. app/crm/models.py.
"""

import re
from datetime import date
from typing import Optional

# 1904 — тот же приём, что в app/crm/service.py::_validate_birthday:
# произвольный високосный год, чтобы 29 февраля проходило проверку.
_LEAP_YEAR_FOR_VALIDATION = 1904

# "дд.мм" — год, если есть, разбирается тем же паттерном, но отбрасывается
# (не (?:\.\d{2,4})? как незахватывающая — а отдельная необязательная
# группа, чтобы вырезать из текста весь найденный фрагмент целиком,
# включая год, если он был написан).
_BIRTHDAY_PATTERN = re.compile(r"(?<!\w)(\d{1,2})\.(\d{1,2})(?:\.\d{2,4})?(?!\w)")


def extract_birthday(text: str) -> tuple[Optional[int], Optional[int], str]:
    """Найти первую дату вида "дд.мм[.гггг]" в тексте. (None, None, text)
    — дата не найдена или найденные день/месяц не образуют существующую
    календарную дату (например "31.02")."""
    match = _BIRTHDAY_PATTERN.search(text)
    if match is None:
        return None, None, text

    day, month = int(match.group(1)), int(match.group(2))
    try:
        date(_LEAP_YEAR_FOR_VALIDATION, month, day)
    except ValueError:
        return None, None, text

    remaining = text[: match.start()] + text[match.end() :]
    remaining = re.sub(r"\s{2,}", " ", remaining).strip(" ,:—-")
    return month, day, remaining
