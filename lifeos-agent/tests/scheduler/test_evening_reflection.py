from unittest.mock import AsyncMock

from app.ai.client import AIServiceError
from app.proactive.questions import EVENING_JOURNAL_PROMPTS
from app.scheduler.evening_reflection import build_evening_reflection_prompt


async def test_ai_question_used_when_available():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Что сегодня заставило тебя улыбнуться?  "

    question = await build_evening_reflection_prompt(ai_client)

    assert question == "Что сегодня заставило тебя улыбнуться?"


async def test_falls_back_to_bank_without_ai_client():
    question = await build_evening_reflection_prompt(None)

    assert question in EVENING_JOURNAL_PROMPTS


async def test_falls_back_to_bank_on_ai_error():
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    question = await build_evening_reflection_prompt(ai_client)

    assert question in EVENING_JOURNAL_PROMPTS


async def test_falls_back_to_bank_on_empty_ai_response():
    ai_client = AsyncMock()
    ai_client.complete.return_value = "   "

    question = await build_evening_reflection_prompt(ai_client)

    assert question in EVENING_JOURNAL_PROMPTS
