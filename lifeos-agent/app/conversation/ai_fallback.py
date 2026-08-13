"""
LLM-фолбэк для разбора намерения (см. specs/003-conversation.md).

Вызывается ТОЛЬКО когда rule-based парсер (parser.py) не смог понять
сообщение. Любая ошибка — сеть, невалидный JSON, неизвестный intent —
тихо превращается в None: фолбэк никогда не должен уронить бота или
показать пользователю техническую ошибку.
"""

import json
import logging
from datetime import date, datetime, time

from app.ai.client import AIClient, AIServiceError
from app.conversation.intent import Intent, ParsedIntent

logger = logging.getLogger(__name__)


def _system_prompt() -> str:
    # Дата подставляется на каждый вызов (не константа) — без неё модель
    # не знает "сегодня" и может додумать произвольный год для due_date
    # (баг, найденный в проактивных подсказках, см. ai_extract.py).
    return (
        f"Сегодня {date.today().isoformat()}. "
        "Ты разбираешь сообщение пользователя личного ассистента задач на русском "
        "языке. Верни СТРОГО JSON без пояснений: "
        '{"intent": "add_task|list_tasks|complete_task|delete_task|help", '
        '"title": строка или null, "due_date": "YYYY-MM-DD" или null}. '
        "intent=add_task — если сообщение похоже на просьбу запомнить дело; "
        "title — краткое название дела без даты; "
        "due_date — если в сообщении есть срок (относительно сегодняшней даты "
        "выше), иначе null."
    )


async def parse_intent_with_ai(text: str, ai_client: AIClient) -> ParsedIntent | None:
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": text},
    ]

    try:
        raw = await ai_client.complete(
            messages, response_format={"type": "json_object"}
        )
        data = json.loads(raw)
        intent = Intent(data["intent"])
        title = data.get("title") or None
        due_date = _parse_due_date(data.get("due_date"))
    except (AIServiceError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("AI fallback не смог разобрать сообщение: %s", exc)
        return None

    return ParsedIntent(intent=intent, title=title, due_date=due_date)


def _parse_due_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed_date = date.fromisoformat(value)
    return datetime.combine(parsed_date, time(hour=9)).astimezone()
