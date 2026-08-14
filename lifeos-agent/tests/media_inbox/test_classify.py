from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.media_inbox.classify import classify_image


async def test_classify_sketch_without_title():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"category": "sketch", "title": null}'

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result.category == "sketch"
    assert result.title is None


async def test_classify_movie_with_title():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"category": "movie", "title": "Дюна"}'

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result.category == "movie"
    assert result.title == "Дюна"


async def test_classify_strips_whitespace_title():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"category": "book", "title": "  Дюна  "}'

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result.title == "Дюна"


async def test_classify_empty_title_becomes_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"category": "movie", "title": "   "}'

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result.title is None


async def test_classify_invalid_category_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"category": "podcast", "title": null}'

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result is None


async def test_classify_malformed_json_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "not json at all"

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result is None


async def test_classify_non_dict_json_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "[1, 2, 3]"

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result is None


async def test_classify_ai_error_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    result = await classify_image(b"bytes", "image/jpeg", ai_client)

    assert result is None
