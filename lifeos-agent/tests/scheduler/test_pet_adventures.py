"""app/scheduler/pet_adventures.py — прямая копия паттерна
tests/scheduler/test_persona_nudges.py::test_generate_nudge_text_*."""

from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.assistant.personas import Persona
from app.scheduler.pet_adventures import generate_adventure_text


async def test_generate_adventure_text_returns_stripped_ai_reply():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Нашёл клевер с четырьмя листьями.  "

    text = await generate_adventure_text(ai_client, Persona.TRAINER)

    assert text == "Нашёл клевер с четырьмя листьями."


async def test_generate_adventure_text_returns_none_on_ai_error():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await generate_adventure_text(ai_client, Persona.BUTLER)

    assert text is None


async def test_generate_adventure_text_returns_none_on_empty_reply():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "   "

    text = await generate_adventure_text(ai_client, Persona.BUTLER)

    assert text is None
