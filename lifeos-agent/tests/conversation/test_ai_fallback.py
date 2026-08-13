from datetime import date
from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.conversation.ai_fallback import parse_intent_with_ai
from app.conversation.intent import Intent


async def test_valid_json_response_is_parsed():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"intent": "add_task", "title": "Позвонить маме", "due_date": "2026-08-14"}'
    )

    result = await parse_intent_with_ai("не забыть про маму", ai_client)

    assert result is not None
    assert result.intent is Intent.ADD_TASK
    assert result.title == "Позвонить маме"
    assert result.due_date is not None
    assert result.due_date.date().isoformat() == "2026-08-14"


async def test_valid_json_without_due_date():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"intent": "list_tasks", "title": null, "due_date": null}'
    )

    result = await parse_intent_with_ai("что там у меня", ai_client)

    assert result is not None
    assert result.intent is Intent.LIST_TASKS
    assert result.title is None
    assert result.due_date is None


async def test_invalid_json_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "это не json"

    result = await parse_intent_with_ai("что-то странное", ai_client)

    assert result is None


async def test_unknown_intent_value_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"intent": "do_something_weird", "title": null, "due_date": null}'
    )

    result = await parse_intent_with_ai("что-то странное", ai_client)

    assert result is None


async def test_missing_intent_key_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"title": "X", "due_date": null}'

    result = await parse_intent_with_ai("что-то странное", ai_client)

    assert result is None


async def test_ai_service_error_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    result = await parse_intent_with_ai("что-то странное", ai_client)

    assert result is None


async def test_invalid_due_date_format_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"intent": "add_task", "title": "X", "due_date": "не дата"}'
    )

    result = await parse_intent_with_ai("что-то странное", ai_client)

    assert result is None


async def test_system_prompt_includes_todays_date():
    # Баг: AI без текущей даты в промпте додумывал произвольный год для
    # due_date (см. историю с целью "Протестировать работу бота" и
    # дедлайном 2023). Дата должна быть в system-сообщении на каждый вызов.
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"intent": "add_task", "title": "X", "due_date": null}'
    )

    await parse_intent_with_ai("что-то", ai_client)

    messages = ai_client.complete.await_args.args[0]
    system_message = next(m["content"] for m in messages if m["role"] == "system")
    assert date.today().isoformat() in system_message
