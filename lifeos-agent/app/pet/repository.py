"""
Репозиторий питомца — единственное место с SQL к таблице `pets`.
Бизнес-логика (голод/настроение/жив ли) — в service.py.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pet.models import Pet


class PetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, telegram_user_id: int) -> Pet | None:
        query = select(Pet).where(Pet.telegram_user_id == telegram_user_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, telegram_user_id: int, now: datetime) -> Pet:
        pet = Pet(telegram_user_id=telegram_user_id, last_fed_at=now)
        self._session.add(pet)
        await self._session.commit()
        await self._session.refresh(pet)
        return pet

    async def feed(self, pet: Pet, when: datetime) -> Pet:
        pet.last_fed_at = when
        self._session.add(pet)
        await self._session.commit()
        await self._session.refresh(pet)
        return pet

    async def revive(self, pet: Pet, when: datetime) -> Pet:
        pet.last_fed_at = when
        pet.deaths_count += 1
        self._session.add(pet)
        await self._session.commit()
        await self._session.refresh(pet)
        return pet

    # --- Опрашивающая джоба (app/telegram/jobs.py::send_farm_pet_notifications_job) ---

    async def list_all(self) -> list[Pet]:
        """Все питомцы, без фильтра по telegram_user_id — проект
        single-user (тот же приём, что list_due_ready_notifications у
        фермы). Голод/состояние здесь не считается — это чистая функция
        от last_fed_at (см. app/pet/service.py), в SQL её не выразить,
        поэтому джоба-опрос вычисляет её сама после загрузки."""
        result = await self._session.execute(select(Pet))
        return list(result.scalars().all())

    async def mark_hungry_notified(self, pet: Pet, when: datetime) -> Pet:
        pet.hungry_notified_at = when
        self._session.add(pet)
        await self._session.commit()
        await self._session.refresh(pet)
        return pet
