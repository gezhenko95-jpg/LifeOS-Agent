"""
Репозиторий для отметок визита.

Единственное место, где выполняются SQL-запросы к таблице `checkins`.
Никакой бизнес-логики (расчёт монет/стрика — в app/rewards/coins.py и
app/habits/streaks.py).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rewards.models import Checkin


class RewardsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_checkin_on(self, telegram_user_id: int, day: date) -> bool:
        query = select(Checkin).where(
            Checkin.telegram_user_id == telegram_user_id, Checkin.checked_on == day
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def add_checkin(self, telegram_user_id: int, day: date) -> Checkin:
        checkin = Checkin(telegram_user_id=telegram_user_id, checked_on=day)
        self._session.add(checkin)
        await self._session.commit()
        await self._session.refresh(checkin)
        return checkin

    async def list_days(self, telegram_user_id: int) -> set[date]:
        query = select(Checkin.checked_on).where(
            Checkin.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        return set(result.scalars().all())
