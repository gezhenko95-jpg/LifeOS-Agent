"""
Rule-based разбор намерения пользователя (без LLM, см. specs/003-conversation.md).
"""

import re
from typing import Optional

from app.conversation.date_parser import extract_due_date, extract_recurrence
from app.conversation.intent import Intent, ParsedIntent

_HELP_KEYWORDS = ("/help", "помощь", "что ты умеешь")
_LIST_KEYWORDS = ("/tasks", "покажи", "список задач", "мои задачи")
# Вопрос про конкретный день («что на завтра») — не путать с ADD_TASK: дата
# в тексте есть, но это вопрос, а не новое дело. Без даты в тексте — просто
# LIST_TASKS (см. QUERY_BY_DATE-ветку в parse_intent).
_QUERY_BY_DATE_KEYWORDS = (
    "что на",
    "что у меня на",
    "что было на",
    "что запланировано",
    "какие задачи",
    "какие дела",
    "что я собирался",
    "что я планировал",
)
# Порядок не важен для распознавания intent (см. _contains_any), но для
# извлечения query (см. _extract_recall_query) вырезаются ВСЕ найденные
# фразы разом — иначе в "напомни, что я говорил про X" после удаления
# только "напомни" в query остаётся филлер "что я говорил про".
_RECALL_KEYWORDS = (
    "напомни",
    "вспомни",
    "что я говорил про",
    "что я говорил о",
    "что я говорил",
    "что ты знаешь про",
    "что ты знаешь о",
)
_RECALL_CONNECTOR_PATTERN = re.compile(r"^[,\s]*(?:про|о|об)\b", re.IGNORECASE)
_COMPLETE_KEYWORDS = ("выполнил", "сделал", "готово", "закрой")
_DELETE_KEYWORDS = ("удали", "убери", "отмени")
_HIGH_PRIORITY_KEYWORDS = ("важно", "срочно")
_LIST_HABITS_KEYWORDS = ("привычки",)
# С пробелом — чтобы отличать команду («привычка чтение») от разговорного
# упоминания слова «привычка» внутри обычной фразы.
_HABIT_DONE_KEYWORD = "привычка "
# Только в начале сообщения — иначе "купить дневник" стало бы записью
# в дневник вместо задачи.
_JOURNAL_KEYWORDS = ("дневник", "рефлексия", "итоги дня")


def parse_intent(text: str) -> ParsedIntent:
    stripped = text.strip()
    lowered = stripped.lower()

    if _contains_any(lowered, _HELP_KEYWORDS):
        return ParsedIntent(intent=Intent.HELP)

    if _contains_any(lowered, _LIST_KEYWORDS):
        return ParsedIntent(intent=Intent.LIST_TASKS)

    if _contains_any(lowered, _QUERY_BY_DATE_KEYWORDS):
        due_date, _ = extract_due_date(stripped)
        if due_date is not None:
            return ParsedIntent(intent=Intent.QUERY_TASKS_BY_DATE, due_date=due_date)
        return ParsedIntent(intent=Intent.LIST_TASKS)

    if _contains_any(lowered, _RECALL_KEYWORDS):
        query = _extract_recall_query(stripped)
        return ParsedIntent(intent=Intent.RECALL, title=query or None)

    if _contains_any(lowered, _LIST_HABITS_KEYWORDS):
        return ParsedIntent(intent=Intent.LIST_HABITS)

    if _HABIT_DONE_KEYWORD in lowered:
        return ParsedIntent(
            intent=Intent.HABIT_DONE,
            title=_remove_keyword(stripped, "привычка"),
        )

    keyword = _contains_any(lowered, _COMPLETE_KEYWORDS)
    if keyword:
        return ParsedIntent(
            intent=Intent.COMPLETE_TASK, title=_remove_keyword(stripped, keyword)
        )

    keyword = _contains_any(lowered, _DELETE_KEYWORDS)
    if keyword:
        return ParsedIntent(
            intent=Intent.DELETE_TASK, title=_remove_keyword(stripped, keyword)
        )

    journal_content = _extract_journal_entry(stripped, lowered)
    if journal_content is not None:
        return ParsedIntent(intent=Intent.JOURNAL_ENTRY, title=journal_content or None)

    priority, without_priority = _extract_priority(stripped)
    recurrence, without_recurrence = extract_recurrence(without_priority)
    due_date, remaining = extract_due_date(without_recurrence)
    return ParsedIntent(
        intent=Intent.ADD_TASK,
        title=remaining.strip(),
        due_date=due_date,
        priority=priority,
        recurrence=recurrence,
    )


def _contains_any(lowered: str, keywords: tuple[str, ...]) -> Optional[str]:
    for keyword in keywords:
        if keyword in lowered:
            return keyword
    return None


def _remove_keyword(text: str, keyword: str) -> str:
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    cleaned = pattern.sub("", text, count=1)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _extract_recall_query(stripped: str) -> str:
    """Вырезать все триггерные фразы (не только первую совпавшую — в
    "напомни, что я говорил про X" их две), затем висящий предлог
    "про/о/об" в начале и лишние пробелы/пунктуацию."""
    text = stripped
    for phrase in _RECALL_KEYWORDS:
        text = re.sub(re.escape(phrase), "", text, count=1, flags=re.IGNORECASE)
    text = _RECALL_CONNECTOR_PATTERN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,:")


def _extract_journal_entry(stripped: str, lowered: str) -> Optional[str]:
    """Вернуть текст записи, если сообщение начинается с триггерного слова.

    None — триггерного слова нет вообще (не JOURNAL_ENTRY);
    "" — триггерное слово есть, но текста после него нет.
    """
    for keyword in _JOURNAL_KEYWORDS:
        if lowered.startswith(keyword):
            return stripped[len(keyword) :].lstrip(":").strip()
    return None


def _extract_priority(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for keyword in _HIGH_PRIORITY_KEYWORDS:
        if keyword in lowered:
            return "high", _remove_keyword(text, keyword)
    return "normal", text
