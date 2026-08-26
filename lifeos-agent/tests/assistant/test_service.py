"""
AssistantService — repository замокан.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from app.assistant.models import AssistantSettings
from app.assistant.personas import Persona
from app.assistant.service import AssistantService


def _settings(
    persona: str = "butler",
    last_nudge_sent_on: date | None = None,
    last_nudge_trigger: str | None = None,
) -> AssistantSettings:
    return AssistantSettings(
        id=1,
        telegram_user_id=1,
        persona=persona,
        last_nudge_sent_on=last_nudge_sent_on,
        last_nudge_trigger=last_nudge_trigger,
    )


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


# --- Дедуп незапланированных сообщений (specs/027-butler-personas-phase2.md, п.2) -


async def test_get_today_nudge_trigger_returns_none_when_never_sent():
    repository = AsyncMock()
    repository.get_or_create.return_value = _settings()
    service = AssistantService(repository)

    assert await service.get_today_nudge_trigger(1) is None


async def test_get_today_nudge_trigger_returns_none_for_a_past_day():
    repository = AsyncMock()
    repository.get_or_create.return_value = _settings(
        last_nudge_sent_on=date.today() - timedelta(days=1),
        last_nudge_trigger="habit_streak:1",
    )
    service = AssistantService(repository)

    assert await service.get_today_nudge_trigger(1) is None


async def test_get_today_nudge_trigger_returns_key_sent_today():
    repository = AsyncMock()
    repository.get_or_create.return_value = _settings(
        last_nudge_sent_on=date.today(), last_nudge_trigger="habit_streak:1"
    )
    service = AssistantService(repository)

    assert await service.get_today_nudge_trigger(1) == "habit_streak:1"


async def test_record_nudge_sent_persists_today_and_key():
    repository = AsyncMock()
    settings = _settings()
    repository.get_or_create.return_value = settings
    repository.save.side_effect = lambda s: s
    service = AssistantService(repository)

    await service.record_nudge_sent(1, "task_overdue:5")

    assert settings.last_nudge_sent_on == date.today()
    assert settings.last_nudge_trigger == "task_overdue:5"
    repository.save.assert_awaited_once_with(settings)
