"""
Репозиторий настроек персонажа. Одна строка на пользователя —
get_or_create с дефолтом при первом обращении, отдельной команды
"инициализировать" не требуется.
"""

from sqlalchemy import select

from app.assistant.models import AssistantSettings
from app.assistant.personas import DEFAULT_PERSONA
from app.core.repository import BaseRepository


class AssistantRepository(BaseRepository[AssistantSettings]):
    model = AssistantSettings

    async def get_or_create(self, telegram_user_id: int) -> AssistantSettings:
        query = select(AssistantSettings).where(
            AssistantSettings.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        settings = result.scalar_one_or_none()
        if settings is not None:
            return settings

        settings = AssistantSettings(
            telegram_user_id=telegram_user_id, persona=DEFAULT_PERSONA.value
        )
        return await self.add(settings)
