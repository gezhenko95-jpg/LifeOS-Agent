"""
Извлечение суммы денег из текста на русском языке (без LLM).

Поддерживается:
- целое и дробное число: «1200», «1200.50», «1200,50»;
- множитель «тысяча»: «1.5к», «2к», «3 тыс», «3 тысячи»;
- необязательная валютная подпись после числа: «руб», «рублей», «р»,
  «₽» — распознаётся, но не влияет на результат (рубли — единственная
  валюта, см. specs/017-finance.md, "Что НЕ входит").

Контракт — как у date_parser.py::extract_due_date: (значение или None,
остаток текста без найденного фрагмента).
"""

import re
from typing import Optional

# Число (целое или дробное через "." либо ",") — первое найденное в
# тексте, не обёрнутое в буквы/цифры с обеих сторон (иначе "3" из
# "3-комнатная" тоже считалось бы суммой).
# Множитель "к"/"тыс[ячи/яч]" сразу после числа (через необязательный
# пробел) — умножает на 1000. Валютная подпись после — просто
# распознаётся и отбрасывается вместе с числом.
_AMOUNT_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(к|тыс\.?|тысячи?|тысяч)?"
    r"(?:\s*(?:руб(?:лей|ля)?|р\.?|₽))?(?!\w)",
    re.IGNORECASE,
)


def extract_amount(text: str) -> tuple[Optional[int], str]:
    """Найти первую сумму в тексте. None, если чисел нет вообще, или
    единственное найденное число оказалось <= 0 после округления (сумма
    не может быть нулевой/отрицательной, см. FinanceService.add_transaction).

    Округление до целых рублей — сознательное упрощение (копейки не
    считаем, ADR-004): "1200.50" → 1200 (не 1201 — банковское округление
    вниз здесь не принципиально, это не бухгалтерия)."""
    match = _AMOUNT_PATTERN.search(text)
    if match is None:
        return None, text

    raw_number = match.group(1).replace(",", ".")
    try:
        number = float(raw_number)
    except ValueError:
        return None, text

    multiplier = (match.group(2) or "").lower()
    if multiplier.startswith("к") or multiplier.startswith("тыс"):
        number *= 1000

    amount = int(number)
    if amount <= 0:
        return None, text

    remaining = text[: match.start()] + text[match.end() :]
    remaining = re.sub(r"\s{2,}", " ", remaining).strip(" ,:—-")
    return amount, remaining
