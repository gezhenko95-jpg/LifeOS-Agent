"""
Assistant Service (specs/020-butler-personas.md) — какой персонаж
сейчас активен у пользователя. Вся бизнес-логика здесь, Repository —
только БД, API/боту достаётся только этот сервис.
"""

from app.assistant.personas import DEFAULT_PERSONA, Persona
from app.assistant.repository import AssistantRepository


class AssistantService:
    def __init__(self, repository: AssistantRepository) -> None:
        self._repository = repository

    async def get_persona(self, telegram_user_id: int) -> Persona:
        settings = await self._repository.get_or_create(telegram_user_id)
        try:
            return Persona(settings.persona)
        except ValueError:
            # Неизвестное значение в БД (например, после отката кода на
            # версию с меньшим набором персонажей) — тихий откат на
            # дефолт, а не 500-ка на ровном месте.
            return DEFAULT_PERSONA

    async def set_persona(self, telegram_user_id: int, persona: Persona) -> Persona:
        settings = await self._repository.get_or_create(telegram_user_id)
        settings.persona = persona.value
        await self._repository.save(settings)
        return persona
