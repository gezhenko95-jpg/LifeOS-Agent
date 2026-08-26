"""
Разговорный AI-фолбэк персонажа (specs/020-butler-personas.md).

Вызывается ТОЛЬКО когда parser.py распознал сообщение как Intent.CHAT
(вопрос или явная реплика собеседнику — см. parser.py), то есть НЕ как
попытку создать задачу. Ответ — обычная прозаическая фраза персонажа,
не JSON, как у ai_fallback.py. Любая ошибка AI — сеть, пустой ответ —
тихо превращается в None: вызывающий код (ConversationEngine) откатывается
на прежнее поведение (сообщение становится задачей), фолбэк никогда не
теряет сообщение пользователя молча.
"""

import logging

from app.ai.client import AIClient, AIServiceError
from app.assistant.personas import Persona, build_insight_prompt

logger = logging.getLogger(__name__)

_TASK_INSTRUCTION = (
    "Пользователь написал тебе как собеседнику (не задача, не команда). "
    "Ответь в своём характере 2-4 предложениями (примерно до 70 слов) — "
    "практично и по существу, с конкретным советом, мнением или встречным "
    "вопросом, а не пустой репликой. Учитывай контекст о пользователе "
    "ниже, если он есть и релевантен, но не пересказывай его. На русском "
    "языке, без предисловий, без кавычек и markdown. Верни только текст "
    "ответа, ничего больше."
)


def _system_prompt(persona: Persona, context: str, history: str) -> str:
    instruction = _TASK_INSTRUCTION
    if context:
        instruction = f"{instruction}\n\nКонтекст о пользователе:\n{context}"
    if history:
        # Отдельный блок, не смешан с "контекстом о пользователе" выше:
        # это конкретные реплики ЭТОГО разговора (specs/027, п.1), не
        # долгосрочные факты — модели нужно различать "что говорилось
        # только что" от "что вообще известно о пользователе".
        instruction = (
            f"{instruction}\n\nНедавние реплики этого разговора "
            f"(старые сверху):\n{history}"
        )
    return build_insight_prompt(persona, instruction)


async def generate_chat_reply(
    text: str,
    persona: Persona,
    ai_client: AIClient,
    context: str = "",
    history: str = "",
) -> str | None:
    messages = [
        {"role": "system", "content": _system_prompt(persona, context, history)},
        {"role": "user", "content": text},
    ]
    try:
        reply = await ai_client.complete(messages)
    except AIServiceError as exc:
        logger.warning("AI не сгенерировал разговорный ответ: %s", exc)
        return None

    reply = reply.strip()
    return reply or None
