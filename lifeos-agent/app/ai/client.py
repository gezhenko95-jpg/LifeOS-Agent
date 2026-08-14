"""
AI Service — тонкий клиент к OpenRouter (OpenAI-совместимый API).

Используется как fallback в Conversation Engine (см.
app/conversation/ai_fallback.py, specs/003-conversation.md) — не вызывается
напрямую из API/БД, только из сервисного слоя, как и требует ARCHITECTURE.md.
"""

import httpx

from app.core.config import Settings, get_settings

# 20s, не 10 — vision-запросы (классификация изображений, см.
# app/media_inbox/classify.py) идут дольше обычных текстовых.
_TIMEOUT_SECONDS = 20.0


class AIServiceError(Exception):
    """Любая ошибка вызова AI Service: сеть, таймаут, не-200, битый ответ."""


class AIClient:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
    ) -> str:
        payload: dict = {"model": self._model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise AIServiceError(f"Ошибка сети при вызове AI Service: {exc}") from exc

        if response.status_code != 200:
            raise AIServiceError(
                f"AI Service вернул статус {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AIServiceError(f"Некорректный ответ AI Service: {exc}") from exc


def get_ai_client(settings: Settings | None = None) -> AIClient | None:
    """Собрать AIClient из настроек, либо None, если ключ не задан."""
    settings = settings or get_settings()
    if not settings.openrouter_api_key:
        return None
    return AIClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
    )
