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
