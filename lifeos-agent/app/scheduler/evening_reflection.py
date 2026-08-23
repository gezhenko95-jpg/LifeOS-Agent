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
from app.assistant.personas import DEFAULT_PERSONA, Persona, build_insight_prompt
from app.proactive.questions import EVENING_JOURNAL_PROMPTS

logger = logging.getLogger(__name__)

# Единственное сознательное исключение из общего лимита "2-4 предложения"
# (specs/020-butler-personas.md) — это ОДИН вопрос, не абзац-вставка,
# развёрнутый вопрос звучал бы как лекция перед сном.
_TASK_INSTRUCTION = (
    "Придумай ОДИН короткий (не более 25 слов) тёплый, конкретный вопрос "
    'для вечерней дневниковой рефлексии — не банальное "как прошёл '
    'день", а что-то, на что по-настоящему хочется ответить. Вопрос '
    "должен звучать в твоём характере. На русском языке, без "
    "предисловий, без кавычек и markdown. Верни только текст вопроса, "
    "ничего больше."
)


def _system_prompt(persona: Persona) -> str:
    return build_insight_prompt(persona, _TASK_INSTRUCTION)


async def build_evening_reflection_prompt(
    ai_client: AIClient | None, persona: Persona = DEFAULT_PERSONA
) -> str:
    if ai_client is not None:
        question = await _generate(ai_client, persona)
        if question:
            return question
    return random.choice(EVENING_JOURNAL_PROMPTS)


async def _generate(ai_client: AIClient, persona: Persona) -> str | None:
    messages = [
        {"role": "system", "content": _system_prompt(persona)},
        {"role": "user", "content": "Придумай вопрос для сегодняшнего вечера."},
    ]
    try:
        question = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI не сгенерировал вечерний вопрос: %s", exc)
        return None

    question = question.strip()
    return question or None
