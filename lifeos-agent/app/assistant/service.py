"""
Assistant Service (specs/020-butler-personas.md) — какой персонаж
сейчас активен у пользователя. Вся бизнес-логика здесь, Repository —
только БД, API/боту достаётся только этот сервис.
"""

from datetime import date

from app.assistant.personas import DEFAULT_PERSONA, Persona
from app.assistant.repository import AssistantRepository


class AssistantService:
    def __init__(self, repository: AssistantRepository) -> None:
        self._repository = repository

    async def get_today_nudge_trigger(self, telegram_user_id: int) -> str | None:
        """Ключ триггера, по которому персонаж УЖЕ написал незапланированно
        сегодня (specs/027-butler-personas-phase2.md, п.2) — None, если
        сегодня ещё не писал (или это другой день). Вызывающий код
        (app/telegram/jobs.py) передаёт его как exclude_trigger_key во
        второй сегодняшний слот проверки, чтобы не долбить тем же
        поводом дважды, но при этом дать шанс НОВОМУ поводу."""
        settings = await self._repository.get_or_create(telegram_user_id)
        if settings.last_nudge_sent_on == date.today():
            return settings.last_nudge_trigger
        return None

    async def record_nudge_sent(self, telegram_user_id: int, trigger_key: str) -> None:
        settings = await self._repository.get_or_create(telegram_user_id)
        settings.last_nudge_sent_on = date.today()
        settings.last_nudge_trigger = trigger_key
        await self._repository.save(settings)

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
