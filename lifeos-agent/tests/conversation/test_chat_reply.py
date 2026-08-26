"""
generate_chat_reply — specs/020-butler-personas.md.
"""

from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.assistant.personas import Persona
from app.conversation.chat_reply import generate_chat_reply


async def test_returns_stripped_reply_on_success():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Хороший вопрос, давай разберёмся.  "

    reply = await generate_chat_reply("как дела?", Persona.BUTLER, ai_client)

    assert reply == "Хороший вопрос, давай разберёмся."


async def test_uses_persona_character_sheet_in_system_prompt():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Ответ."

    await generate_chat_reply("как дела?", Persona.TRAINER, ai_client)

    messages = ai_client.complete.call_args.args[0]
    assert "тренер" in messages[0]["content"].lower()


async def test_includes_context_when_given():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Ответ."

    await generate_chat_reply(
        "как дела?", Persona.BUTLER, ai_client, context="- люблю бегать по утрам"
    )

    messages = ai_client.complete.call_args.args[0]
    assert "люблю бегать по утрам" in messages[0]["content"]


async def test_includes_history_when_given():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Ответ."

    await generate_chat_reply(
        "а второй вариант?",
        Persona.BUTLER,
        ai_client,
        history="Пользователь: подскажи вариант отпуска\nТы: Сочи или Кавказ.",
    )

    messages = ai_client.complete.call_args.args[0]
    assert "Сочи или Кавказ" in messages[0]["content"]


async def test_returns_none_on_ai_error():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    reply = await generate_chat_reply("привет", Persona.BUTLER, ai_client)

    assert reply is None


async def test_returns_none_on_empty_response():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "   "

    reply = await generate_chat_reply("привет", Persona.BUTLER, ai_client)

    assert reply is None
