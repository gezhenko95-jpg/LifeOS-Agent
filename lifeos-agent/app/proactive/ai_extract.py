"""
AI-разбор ответа на проактивный вопрос (см. specs/006-proactive-engagement.md).

Копирует паттерн app/conversation/ai_fallback.py: любая ошибка — сеть,
невалидный JSON, неизвестное значение — тихо превращается в None. Вызывать
только когда есть открытый PendingPrompt (см. ConversationEngine).
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.ai.client import AIClient, AIServiceError
from app.memory.models import MemoryType

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"create_goal", "create_habit", "save_memory", "unrelated"}
_VALID_MEMORY_TYPES = {
    MemoryType.FACT.value,
    MemoryType.PREFERENCE.value,
    MemoryType.PROJECT.value,
}


def _system_prompt() -> str:
    # Дата подставляется на каждый вызов (не константа) — без неё модель
    # не знает "сегодня" и может додумать произвольный год для target_date
    # (реальный найденный баг: цель с дедлайном в 2023).
    return (
        f"Сегодня {date.today().isoformat()}. "
        "Ты помогаешь личному ассистенту разобрать ответ пользователя на "
        "заданный ботом вопрос. Тебе дана категория вопроса, сам вопрос и "
        "ответ пользователя на русском языке. Реши, что сделать с ответом, "
        "ИСХОДЯ ИЗ ЕГО СОДЕРЖАНИЯ (категория — только подсказка, не жёсткое "
        "правило). Верни СТРОГО JSON без пояснений:\n"
        '{"action": "create_goal|create_habit|save_memory|unrelated", '
        '"title": строка или null, "target_date": "YYYY-MM-DD" или null, '
        '"memory_type": "fact|preference|project" или null, '
        '"content": строка или null}\n'
        "action=create_goal — ответ описывает цель; title — короткое "
        "название, target_date — дедлайн относительно сегодняшней даты "
        "выше, если назван, иначе null.\n"
        "action=create_habit — ответ описывает привычку; title — короткое "
        "название.\n"
        "action=save_memory — ответ это факт/предпочтение/описание проекта, "
        "не тянущий на цель или привычку; memory_type — какой из трёх; "
        "content — сам факт кратко.\n"
        "action=unrelated — ответ не связан с вопросом (например, это новая "
        "задача или команда боту, а не ответ)."
    )


@dataclass
class PromptAnswer:
    action: str
    title: Optional[str] = None
    target_date: Optional[date] = None
    memory_type: Optional[str] = None
    content: Optional[str] = None


async def extract_prompt_answer(
    category: str, question_text: str, user_reply: str, ai_client: AIClient
) -> Optional[PromptAnswer]:
    user_content = (
        f"Категория вопроса: {category}\nВопрос: {question_text}\nОтвет: {user_reply}"
    )
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_content},
    ]

    try:
        raw = await ai_client.complete(
            messages, response_format={"type": "json_object"}
        )
        data = json.loads(raw)
        action = data["action"]
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Неизвестное action: {action}")

        memory_type = data.get("memory_type") or None
        if memory_type is not None and memory_type not in _VALID_MEMORY_TYPES:
            raise ValueError(f"Неизвестный memory_type: {memory_type}")

        target_date = _parse_date(data.get("target_date"))
    except (AIServiceError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("AI не смог разобрать ответ на подсказку: %s", exc)
        return None

    return PromptAnswer(
        action=action,
        title=data.get("title") or None,
        target_date=target_date,
        memory_type=memory_type,
        content=data.get("content") or None,
    )


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)
