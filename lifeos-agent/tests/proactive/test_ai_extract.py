from datetime import date
from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.proactive.ai_extract import extract_prompt_answer


async def test_create_goal_is_parsed():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "create_goal", "title": "Выучить испанский", '
        '"target_date": "2026-12-31", "memory_type": null, "content": null}'
    )

    result = await extract_prompt_answer(
        "goal", "Какая у тебя цель?", "Хочу выучить испанский к концу года", ai_client
    )

    assert result is not None
    assert result.action == "create_goal"
    assert result.title == "Выучить испанский"
    assert result.target_date.isoformat() == "2026-12-31"


async def test_create_habit_is_parsed():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "create_habit", "title": "Медитация", '
        '"target_date": null, "memory_type": null, "content": null}'
    )

    result = await extract_prompt_answer(
        "habit", "Какую привычку хочешь завести?", "Хочу медитировать", ai_client
    )

    assert result is not None
    assert result.action == "create_habit"
    assert result.title == "Медитация"
    assert result.target_date is None


async def test_save_memory_is_parsed():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "save_memory", "title": null, "target_date": null, '
        '"memory_type": "preference", "content": "Любит работать по утрам"}'
    )

    result = await extract_prompt_answer(
        "preference", "Что мне о тебе запомнить?", "Я лучше работаю утром", ai_client
    )

    assert result is not None
    assert result.action == "save_memory"
    assert result.memory_type == "preference"
    assert result.content == "Любит работать по утрам"


async def test_unrelated_reply_is_parsed():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "unrelated", "title": null, "target_date": null, '
        '"memory_type": null, "content": null}'
    )

    result = await extract_prompt_answer(
        "goal", "Какая у тебя цель?", "Купить молоко завтра", ai_client
    )

    assert result is not None
    assert result.action == "unrelated"


async def test_invalid_json_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "это не json"

    result = await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_unknown_action_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "do_something_weird", "title": null, "target_date": null, '
        '"memory_type": null, "content": null}'
    )

    result = await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_unknown_memory_type_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "save_memory", "title": null, "target_date": null, '
        '"memory_type": "goal", "content": "текст"}'
    )

    result = await extract_prompt_answer("reflect", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_invalid_date_format_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "create_goal", "title": "X", "target_date": "не дата", '
        '"memory_type": null, "content": null}'
    )

    result = await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_ai_service_error_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    result = await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_missing_action_key_returns_none():
    ai_client = AsyncMock()
    ai_client.complete.return_value = '{"title": "X"}'

    result = await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    assert result is None


async def test_system_prompt_includes_todays_date():
    # Баг: цель "Протестировать работу бота" получила дедлайн 2023 —
    # AI додумал год, не зная текущей даты. Дата должна быть в
    # system-сообщении на каждый вызов.
    ai_client = AsyncMock()
    ai_client.complete.return_value = (
        '{"action": "unrelated", "title": null, "target_date": null, '
        '"memory_type": null, "content": null}'
    )

    await extract_prompt_answer("goal", "Вопрос?", "ответ", ai_client)

    messages = ai_client.complete.await_args.args[0]
    system_message = next(m["content"] for m in messages if m["role"] == "system")
    assert date.today().isoformat() in system_message
