"""
ConversationEngine + Intent.CHAT (specs/020-butler-personas.md).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.assistant.personas import Persona
from app.conversation.engine import ConversationEngine


@pytest.fixture
def task_service():
    service = AsyncMock()
    service.create_task.return_value = SimpleNamespace(
        title="как дела?", due_date=None, priority="normal", recurrence=None
    )
    return service


@pytest.fixture
def habit_service():
    return AsyncMock()


@pytest.fixture
def memory_service():
    service = AsyncMock()
    service.list_entries.return_value = []
    return service


@pytest.fixture
def assistant_service():
    service = AsyncMock()
    service.get_persona.return_value = Persona.BUTLER
    return service


async def test_chat_reply_used_when_ai_and_persona_available(
    task_service, habit_service, memory_service, assistant_service
):
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Всё хорошо, а у тебя как дела?"
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        assistant_service=assistant_service,
    )

    result = await engine.handle_message(1, "как дела?")

    assert result.text == "Всё хорошо, а у тебя как дела?"
    assert result.created_task is None
    task_service.create_task.assert_not_awaited()


async def test_chat_falls_back_to_task_without_ai_client(
    task_service, habit_service, memory_service, assistant_service
):
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=None,
        assistant_service=assistant_service,
    )

    result = await engine.handle_message(1, "как дела?")

    task_service.create_task.assert_awaited_once()
    assert result.created_task is not None


async def test_chat_falls_back_to_task_without_assistant_service(
    task_service, habit_service, memory_service
):
    ai_client = AsyncMock()
    ai_client.complete.return_value = "не должно быть вызвано"
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        assistant_service=None,
    )

    result = await engine.handle_message(1, "как дела?")

    task_service.create_task.assert_awaited_once()
    assert result.created_task is not None


async def test_chat_falls_back_to_task_on_empty_ai_response(
    task_service, habit_service, memory_service, assistant_service
):
    ai_client = AsyncMock()
    ai_client.complete.return_value = "   "
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        assistant_service=assistant_service,
    )

    result = await engine.handle_message(1, "как дела?")

    task_service.create_task.assert_awaited_once()
    assert result.created_task is not None


async def test_chat_context_uses_recent_memory_entries(
    task_service, habit_service, memory_service, assistant_service
):
    memory_service.list_entries.return_value = [
        SimpleNamespace(content="любит бегать по утрам"),
        SimpleNamespace(content="работает над курсом"),
    ]
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Ответ по существу."
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        assistant_service=assistant_service,
    )

    await engine.handle_message(1, "как дела?")

    messages = ai_client.complete.call_args.args[0]
    system_content = messages[0]["content"]
    assert "любит бегать по утрам" in system_content
    assert "работает над курсом" in system_content


async def test_chat_uses_active_persona_voice(
    task_service, habit_service, memory_service, assistant_service
):
    assistant_service.get_persona.return_value = Persona.TRAINER
    ai_client = AsyncMock()
    ai_client.complete.return_value = "Не сдавайся!"
    engine = ConversationEngine(
        task_service,
        habit_service,
        memory_service,
        ai_client=ai_client,
        assistant_service=assistant_service,
    )

    await engine.handle_message(1, "как дела?")

    messages = ai_client.complete.call_args.args[0]
    assert "тренер" in messages[0]["content"].lower()
