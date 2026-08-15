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
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        embedding_model: str = "openai/text-embedding-3-small",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._embedding_model = embedding_model
        # Один httpx-клиент на всё время жизни AIClient — держит TCP/TLS
        # соединение открытым между вызовами (keep-alive). Раньше каждый
        # complete()/embed() открывал `async with httpx.AsyncClient()`,
        # то есть новое соединение и TLS-хендшейк на КАЖДЫЙ запрос к
        # OpenRouter, +100-300 мс сверх самого запроса (см. AUDIT.md,
        # P-4). get_ai_client() ниже переиспользует один AIClient на
        # процесс, поэтому этот клиент живёт вместе с ботом, а не с
        # одним сообщением.
        self._http = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)

    async def complete(
        self,
        messages: list[dict],
        *,
        response_format: dict | None = None,
    ) -> str:
        payload: dict = {"model": self._model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format

        data = await self._post_json("/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIServiceError(f"Некорректный ответ AI Service: {exc}") from exc

    async def embed(self, text: str) -> list[float]:
        """Вектор embedding для текста (см. specs/011-semantic-memory-
        search.md) — отдельная модель (embedding_model), не chat-модель."""
        payload = {"model": self._embedding_model, "input": text}

        data = await self._post_json("/embeddings", payload)
        try:
            return data["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise AIServiceError(f"Некорректный ответ AI Service: {exc}") from exc

    async def _post_json(self, path: str, payload: dict) -> dict:
        """POST + разбор JSON, общий для complete()/embed(). Раньше эта
        пара (сетевая ошибка → AIServiceError, не-200 → AIServiceError,
        битый JSON → AIServiceError) была продублирована в обоих методах
        дословно."""
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            response = await self._http.post(
                f"{self._base_url}{path}", json=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise AIServiceError(f"Ошибка сети при вызове AI Service: {exc}") from exc

        if response.status_code != 200:
            raise AIServiceError(
                f"AI Service вернул статус {response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise AIServiceError(f"Некорректный ответ AI Service: {exc}") from exc


# Один AIClient (а вместе с ним — один httpx.AsyncClient, см. выше) на
# процесс: раньше каждый вызов get_ai_client() из хендлера/джобы строил
# новый AIClient, обнуляя весь смысл keep-alive-соединения. Ключ — по
# полям, влияющим на сам клиент; настройки приходят из get_settings()
# (тоже кэширован), так что в проде кэш фактически на одну запись.
_client_cache: dict[tuple[str, str, str, str], AIClient] = {}


def get_ai_client(settings: Settings | None = None) -> AIClient | None:
    """Собрать AIClient из настроек, либо None, если ключ не задан."""
    settings = settings or get_settings()
    if not settings.openrouter_api_key:
        return None

    key = (
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.openrouter_base_url,
        settings.openrouter_embedding_model,
    )
    cached = _client_cache.get(key)
    if cached is not None:
        return cached

    client = AIClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        embedding_model=settings.openrouter_embedding_model,
    )
    _client_cache[key] = client
    return client
