"""
"Приключения" питомца (specs/030-more-engagement-features.md, по
мотивам Finch) — раз в день, если питомец сегодня покормлен, короткая
AI-история в голосе персонажа о том, что питомец нашёл на ферме.

Прямая копия паттерна app/scheduler/persona_nudges.py::generate_nudge_text
— тихий None на ошибке AI (фича просто не появляется в сообщении, без
падений и без ретраев в тот же день).
"""

import logging

from app.ai.client import AIClient, AIServiceError
from app.assistant.personas import Persona, build_insight_prompt

logger = logging.getLogger(__name__)

_ADVENTURE_INSTRUCTION = (
    "Придумай короткую (1 предложение, максимум 25 слов) историю о том, "
    "что твой питомец нашёл или увидел сегодня, гуляя по ферме — милую, "
    "тёплую деталь (находка, встреча, наблюдение), без морали и без "
    "совета. Расскажи от своего лица, как будто сам туда заглядывал. На "
    "русском языке, без предисловий, без кавычек и markdown. Верни "
    "только текст, ничего больше."
)


async def generate_adventure_text(ai_client: AIClient, persona: Persona) -> str | None:
    messages = [
        {
            "role": "system",
            "content": build_insight_prompt(persona, _ADVENTURE_INSTRUCTION),
        },
        {"role": "user", "content": "Что нашёл питомец сегодня?"},
    ]
    try:
        text = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI не сгенерировал историю приключения питомца: %s", exc)
        return None

    text = text.strip()
    return text or None
