"""
AI-классификация изображений, присланных боту (Фаза 2 Media Inbox, см.
specs/010-media-inbox.md). LLM здесь оправдан (ADR-004) — понять, что
на картинке, обычным кодом не получится.
"""

import base64
import json
import logging
from dataclasses import dataclass

from app.ai.client import AIClient, AIServiceError

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {"sketch", "movie", "book", "other"}

_SYSTEM_PROMPT = (
    "Ты — классификатор изображений для личного ассистента. Пользователь "
    "прислал картинку. Определи, что на ней, и верни СТРОГО JSON без "
    "markdown и пояснений: "
    '{"category": "sketch"|"movie"|"book"|"other", "title": string|null}. '
    "sketch — рисунок/эскиз/скетч (рукотворное изображение, не фото и не "
    "скриншот интерфейса). movie — постер/скриншот фильма или сериала. "
    "book — обложка/скриншот книги. other — всё остальное. title — "
    "название фильма/книги, ТОЛЬКО если оно реально читается на "
    "картинке; если не уверена или названия нет — null. Если сомневаешься "
    "в категории — выбирай other, не угадывай."
)


@dataclass
class ImageClassification:
    category: str
    title: str | None


async def classify_image(
    image_bytes: bytes, mime_type: str, ai_client: AIClient
) -> ImageClassification | None:
    """None — AI недоступна/ошиблась/вернула мусор. Вызывающий код тихо
    откатывается на category="other" (см. app/media_inbox/service.py) —
    тот же принцип "AI сбоит молча", что и везде в проекте."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            ],
        },
    ]
    try:
        raw = await ai_client.complete(
            messages, response_format={"type": "json_object"}
        )
        data = json.loads(raw)
    except (AIServiceError, json.JSONDecodeError) as exc:
        logger.warning("Классификация изображения не удалась: %s", exc)
        return None

    if not isinstance(data, dict):
        return None

    category = data.get("category")
    if category not in _VALID_CATEGORIES:
        return None

    title = data.get("title")
    title = title.strip() if isinstance(title, str) else ""
    return ImageClassification(category=category, title=title or None)
