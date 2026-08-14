"""
Глубокий вечерний дневниковый вопрос для слота 21:00 (см.
flows/009-daily-rhythm.md) — заменяет прежний статичный текст «Как
прошёл день? Напишите дневник: ...». AI придумывает ОДИН вдумчивый
вопрос, на который хочется ответить; при недоступности/ошибке AI —
банк заранее написанных вопросов (questions.py::EVENING_JOURNAL_PROMPTS).
Никогда не блокирует отправку (тот же принцип, что и у остальных
AI-вставок в проекте).
"""

import logging
import random

from app.ai.client import AIClient, AIServiceError
from app.proactive.questions import EVENING_JOURNAL_PROMPTS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты — личный ассистент пользователя. Придумай ОДИН короткий (не "
    "более 20 слов) тёплый, конкретный вопрос для вечерней дневниковой "
    'рефлексии — не банальное "как прошёл день", а что-то, на что '
    "по-настоящему хочется ответить. На русском языке, без предисловий, "
    "без кавычек и markdown. Верни только текст вопроса, ничего больше."
)


async def build_evening_reflection_prompt(ai_client: AIClient | None) -> str:
    if ai_client is not None:
        question = await _generate(ai_client)
        if question:
            return question
    return random.choice(EVENING_JOURNAL_PROMPTS)


async def _generate(ai_client: AIClient) -> str | None:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "Придумай вопрос для сегодняшнего вечера."},
    ]
    try:
        question = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI не сгенерировал вечерний вопрос: %s", exc)
        return None

    question = question.strip()
    return question or None
