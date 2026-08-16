"""
AI Service — тонкий клиент к OpenRouter (OpenAI-совместимый API).

Используется как fallback в Conversation Engine (см.
app/conversation/ai_fallback.py, specs/003-conversation.md) — не вызывается
напрямую из API/БД, только из сервисного слоя, как и требует ARCHITECTURE.md.
"""

import base64

import httpx

from app.core.config import Settings, get_settings

# 20s, не 10 — vision-запросы (классификация изображений, см.
# app/media_inbox/classify.py) идут дольше обычных текстовых.
_TIMEOUT_SECONDS = 20.0

# Транскрипция длинного голосового (до voice_max_duration_seconds, по
# умолчанию 5 мин) может занять дольше, чем обычный chat/embeddings-
# запрос — обычного таймаута мало (см. specs/012-voice-input.md).
_TRANSCRIBE_TIMEOUT_SECONDS = 60.0


class AIServiceError(Exception):
    """Любая ошибка вызова AI Service: сеть, таймаут, не-200, битый ответ."""


class AIClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        embedding_model: str = "openai/text-embedding-3-small",
        transcription_model: str = "openai/whisper-large-v3",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._embedding_model = embedding_model
        self._transcription_model = transcription_model
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

    async def transcribe(self, audio_bytes: bytes, audio_format: str = "ogg") -> str:
        """Голосовое → текст через OpenRouter `/audio/transcriptions`
        (см. specs/012-voice-input.md). Base64 JSON, не multipart — тот
        же путь `_post_json`, что и у complete()/embed(); `ogg` — формат
        по умолчанию, потому что именно в нём Telegram отдаёт голосовые
        сообщения (кодек Opus внутри), а `ogg` — в списке официально
        поддерживаемых форматов и у OpenRouter, и у OpenAI whisper."""
        payload = {
            "model": self._transcription_model,
            "input_audio": {
                "data": base64.b64encode(audio_bytes).decode("ascii"),
                "format": audio_format,
            },
        }

        data = await self._post_json(
            "/audio/transcriptions", payload, timeout=_TRANSCRIBE_TIMEOUT_SECONDS
        )
        try:
            return data["text"]
        except KeyError as exc:
            raise AIServiceError(f"Некорректный ответ AI Service: {exc}") from exc

    async def _post_json(
        self, path: str, payload: dict, timeout: float | None = None
    ) -> dict:
        """POST + разбор JSON, общий для complete()/embed()/transcribe().
        Раньше эта пара (сетевая ошибка → AIServiceError, не-200 →
        AIServiceError, битый JSON → AIServiceError) была продублирована
        в обоих методах дословно. `timeout` — переопределить таймаут
        клиента по умолчанию на один запрос (транскрипция длинного
        голосового может занять дольше обычного chat/embeddings).

        ВАЖНО: `timeout` пробрасывается в httpx только если явно задан —
        httpx трактует явный `timeout=None` как "без таймаута вообще", а
        не "как у клиента по умолчанию" (это два разных значения)."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        kwargs = {"json": payload, "headers": headers}
        if timeout is not None:
            kwargs["timeout"] = timeout

        try:
            response = await self._http.post(f"{self._base_url}{path}", **kwargs)
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
_client_cache: dict[tuple[str, str, str, str, str], AIClient] = {}


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
        settings.openrouter_transcription_model,
    )
    cached = _client_cache.get(key)
    if cached is not None:
        return cached

    client = AIClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        embedding_model=settings.openrouter_embedding_model,
        transcription_model=settings.openrouter_transcription_model,
    )
    _client_cache[key] = client
    return client
