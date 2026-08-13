"""
Репозиторий для PendingPrompt.

Единственное место, где выполняются SQL-запросы к таблице
`pending_prompts`. Одна строка на пользователя — upsert вместо create,
никакой очереди вопросов (см. specs/006-proactive-engagement.md).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.proactive.models import PendingPrompt


class PendingPromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, telegram_user_id: int) -> Optional[PendingPrompt]:
        query = select(PendingPrompt).where(
            PendingPrompt.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def upsert(
        self, telegram_user_id: int, category: str, question_text: str
    ) -> PendingPrompt:
        existing = await self.get_for_user(telegram_user_id)
        if existing is not None:
            existing.category = category
            existing.question_text = question_text
            # server_default=func.now() срабатывает только на INSERT — при
            # перезаписи неотвеченного вопроса обновляем время вручную.
            existing.asked_at = datetime.now(timezone.utc)
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        prompt = PendingPrompt(
            telegram_user_id=telegram_user_id,
            category=category,
            question_text=question_text,
        )
        self._session.add(prompt)
        await self._session.commit()
        await self._session.refresh(prompt)
        return prompt

    async def clear_for_user(self, telegram_user_id: int) -> None:
        existing = await self.get_for_user(telegram_user_id)
        if existing is not None:
            await self._session.delete(existing)
            await self._session.commit()
