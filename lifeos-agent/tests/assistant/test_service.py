"""
AssistantService — repository замокан.
"""

from unittest.mock import AsyncMock

from app.assistant.models import AssistantSettings
from app.assistant.personas import Persona
from app.assistant.service import AssistantService


def _settings(persona: str = "butler") -> AssistantSettings:
    return AssistantSettings(id=1, telegram_user_id=1, persona=persona)


async def test_get_persona_returns_stored_value():
    repository = AsyncMock()
    repository.get_or_create.return_value = _settings("trainer")
    service = AssistantService(repository)

    persona = await service.get_persona(1)

    assert persona is Persona.TRAINER


async def test_get_persona_falls_back_to_default_on_unknown_value():
    repository = AsyncMock()
    repository.get_or_create.return_value = _settings("some_old_persona")
    service = AssistantService(repository)

    persona = await service.get_persona(1)

    assert persona is Persona.BUTLER


async def test_set_persona_persists_and_returns_it():
    repository = AsyncMock()
    settings = _settings("butler")
    repository.get_or_create.return_value = settings
    repository.save.side_effect = lambda s: s
    service = AssistantService(repository)

    result = await service.set_persona(1, Persona.DIRECTOR)

    assert result is Persona.DIRECTOR
    assert settings.persona == "director"
    repository.save.assert_awaited_once_with(settings)
