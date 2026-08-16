import base64
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.ai.client import AIClient, AIServiceError, get_ai_client
from app.core.config import Settings


def _response(status_code: int, json_body: dict | None = None, text: str = ""):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    if json_body is not None:
        return httpx.Response(status_code, json=json_body, request=request)
    return httpx.Response(status_code, text=text, request=request)


def _client() -> AIClient:
    return AIClient(
        api_key="key", model="test-model", base_url="https://openrouter.ai/api/v1"
    )


async def test_complete_returns_content_on_success():
    fake_response = _response(
        200, json_body={"choices": [{"message": {"content": "hello"}}]}
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        result = await _client().complete([{"role": "user", "content": "hi"}])

    assert result == "hello"


async def test_complete_raises_on_non_200():
    fake_response = _response(500, text="server error")

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().complete([{"role": "user", "content": "hi"}])


async def test_complete_raises_on_malformed_response_body():
    fake_response = _response(200, json_body={"unexpected": "shape"})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().complete([{"role": "user", "content": "hi"}])


async def test_complete_raises_on_network_error():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        with pytest.raises(AIServiceError):
            await _client().complete([{"role": "user", "content": "hi"}])


async def test_embed_returns_vector_on_success():
    fake_response = _response(200, json_body={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        result = await _client().embed("тестовая фраза")

    assert result == [0.1, 0.2, 0.3]


async def test_embed_raises_on_non_200():
    fake_response = _response(500, text="server error")

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().embed("текст")


async def test_embed_raises_on_malformed_response_body():
    fake_response = _response(200, json_body={"unexpected": "shape"})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().embed("текст")


async def test_embed_raises_on_network_error():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        with pytest.raises(AIServiceError):
            await _client().embed("текст")


async def test_transcribe_returns_text_on_success():
    fake_response = _response(200, json_body={"text": "купить молоко завтра"})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        result = await _client().transcribe(b"fake-ogg-bytes")

    assert result == "купить молоко завтра"


async def test_transcribe_sends_base64_audio_with_model_and_format():
    fake_response = _response(200, json_body={"text": "x"})
    post_mock = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient.post", new=post_mock):
        await _client().transcribe(b"fake-ogg-bytes", audio_format="ogg")

    payload = post_mock.await_args.kwargs["json"]
    assert payload["model"] == "openai/whisper-large-v3"
    assert payload["input_audio"]["format"] == "ogg"
    assert payload["input_audio"]["data"] == base64.b64encode(b"fake-ogg-bytes").decode(
        "ascii"
    )


async def test_transcribe_raises_on_non_200():
    fake_response = _response(500, text="server error")

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().transcribe(b"fake-ogg-bytes")


async def test_transcribe_raises_on_malformed_response_body():
    fake_response = _response(200, json_body={"unexpected": "shape"})

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        with pytest.raises(AIServiceError):
            await _client().transcribe(b"fake-ogg-bytes")


async def test_transcribe_raises_on_network_error():
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        with pytest.raises(AIServiceError):
            await _client().transcribe(b"fake-ogg-bytes")


async def test_transcribe_uses_longer_timeout_than_complete():
    """Транскрипция длинного голосового может занять дольше обычного
    chat-запроса — должен применяться отдельный, больший таймаут."""
    fake_response = _response(200, json_body={"text": "x"})
    post_mock = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient.post", new=post_mock):
        await _client().transcribe(b"fake-ogg-bytes")

    assert post_mock.await_args.kwargs["timeout"] == 60.0


async def test_complete_does_not_override_client_default_timeout():
    """httpx трактует ЯВНЫЙ timeout=None как "без таймаута вообще", а не
    "как у клиента по умолчанию" — complete()/embed() не должны вообще
    передавать timeout, иначе таймаут клиента (_TIMEOUT_SECONDS) молча
    перестал бы работать для них."""
    fake_response = _response(
        200, json_body={"choices": [{"message": {"content": "hi"}}]}
    )
    post_mock = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient.post", new=post_mock):
        await _client().complete([{"role": "user", "content": "hi"}])

    assert "timeout" not in post_mock.await_args.kwargs


def test_get_ai_client_returns_none_without_key():
    settings = Settings(telegram_bot_token="x", openrouter_api_key="")

    assert get_ai_client(settings) is None


def test_get_ai_client_returns_client_with_key():
    settings = Settings(
        telegram_bot_token="x",
        openrouter_api_key="sk-test",
        openrouter_model="some-model",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )

    client = get_ai_client(settings)

    assert isinstance(client, AIClient)


def test_get_ai_client_reuses_same_instance_across_calls():
    """Раньше каждый вызов строил новый AIClient (и внутри него — новый
    httpx.AsyncClient, новое TCP/TLS соединение на каждый запрос к
    OpenRouter, см. AUDIT.md P-4). Хендлеры и джобы дёргают
    get_ai_client() на каждое сообщение — без переиспользования это
    сводило на нет весь смысл keep-alive."""
    settings = Settings(
        telegram_bot_token="x",
        openrouter_api_key="sk-same",
        openrouter_model="m",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )

    first = get_ai_client(settings)
    second = get_ai_client(settings)

    assert first is second


def test_get_ai_client_reuses_the_underlying_http_client():
    """Не только AIClient один и тот же — httpx.AsyncClient внутри тоже
    не пересоздаётся, иначе keep-alive соединение всё равно рвалось бы
    на каждый вызов."""
    settings = Settings(
        telegram_bot_token="x",
        openrouter_api_key="sk-same-http",
        openrouter_model="m",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )

    first = get_ai_client(settings)
    second = get_ai_client(settings)

    assert first._http is second._http


def test_get_ai_client_gives_separate_instances_for_different_keys():
    """Разный api_key — разный клиент: смешивать соединения/авторизацию
    двух разных конфигураций было бы хуже, чем не кэшировать вовсе."""
    settings_a = Settings(
        telegram_bot_token="x",
        openrouter_api_key="sk-a",
        openrouter_model="m",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )
    settings_b = Settings(
        telegram_bot_token="x",
        openrouter_api_key="sk-b",
        openrouter_model="m",
        openrouter_base_url="https://openrouter.ai/api/v1",
    )

    assert get_ai_client(settings_a) is not get_ai_client(settings_b)
