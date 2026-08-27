"""
PetService — вся бизнес-логика питомца (specs/028-farm-tamagotchi-
rewards.md, фаза 3). Repository — только БД, API — только вызывает
этот сервис.

Composite: кормление тратит сено, а сено — ресурс фермы, поэтому
PetService получает готовый FarmService (тот же приём, что у
build_shop_service/build_farm_service в container.py).

Голод/настроение/состояние — ЧИСТАЯ функция от `last_fed_at`, ничего из
этого не хранится отдельно (см. докстринг app/pet/models.py::Pet). Это
тот же архитектурный выбор, что уже проведён через `total_coins`,
availability семян фермы и т.д.: производное состояние не хранится,
потому что хранимая копия имеет свойство расходиться с первоисточником.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.farm.service import FarmService, InsufficientHayError
from app.pet.models import Pet
from app.pet.repository import PetRepository

# Калибровка от той же экономики, что ферма (specs/028, ответ владельца
# 27.08): грядка — сутки, 10 сена, питомец ест 5/день — то есть ОДНА
# грядка кормит питомца ДВОЕ суток. HUNGER_FULL_HOURS отражает именно
# это: 48 часов без еды — и голод достиг максимума.
HAY_PER_FEED = 5
HUNGER_FULL_HOURS = 48
# "Долгое пренебрежение" (формулировка владельца) — не день просрочки,
# а стабильно пропущенный цикл кормления и затем ещё один:
# 72ч = HUNGER_FULL_HOURS + сутки полного голода до болезни,
# 144ч = HUNGER_FULL_HOURS + трое суток болезни до смерти.
SICK_AFTER_HOURS = 72
DEATH_AFTER_HOURS = 144

PetState = Literal["healthy", "hungry", "sick", "dead"]


class PetError(ValueError):
    """Общий предок ошибок питомца — API ловит его одним except."""


class NoPetError(PetError):
    pass


class AlreadyHasPetError(PetError):
    pass


class PetIsDeadError(PetError):
    pass


class NotDeadError(PetError):
    pass


@dataclass
class PetStatus:
    exists: bool
    hunger: int = 0
    mood: int = 0
    state: PetState | None = None
    last_fed_at: datetime | None = None
    deaths_count: int = 0
    # Момент, когда текущее состояние сменится следующим (голоден →
    # болен → мёртв) — тот же UX-приём, что ready_at у грядок фермы:
    # UI показывает обратный отсчёт, а не просит клиента считать часы.
    next_threshold_at: datetime | None = None


class PetService:
    def __init__(self, repository: PetRepository, farm_service: FarmService) -> None:
        self._repository = repository
        self._farm = farm_service

    async def get_status(self, telegram_user_id: int) -> PetStatus:
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            return PetStatus(exists=False)
        return _status(pet)

    async def adopt(self, telegram_user_id: int) -> PetStatus:
        """Первый питомец на аккаунте. Не путать с revive() — заводить
        нового ПОСЛЕ смерти прежнего осознанно другое действие с другой
        ценой (см. docstring revive)."""
        existing = await self._repository.get(telegram_user_id)
        if existing is not None:
            raise AlreadyHasPetError("Питомец уже есть")
        pet = await self._repository.create(
            telegram_user_id, datetime.now(timezone.utc)
        )
        return _status(pet)

    async def feed(self, telegram_user_id: int) -> PetStatus:
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            raise NoPetError("Сначала заведите питомца")
        status = _status(pet)
        if status.state == "dead":
            # Кормление НЕ воскрешает — иначе смерть ничего бы не стоила
            # (решение владельца: цена бездействия должна быть реальной).
            raise PetIsDeadError("Питомец погиб — нужно похоронить и завести нового")

        available = await self._farm.available_hay(telegram_user_id)
        if available < HAY_PER_FEED:
            raise InsufficientHayError(
                f"Не хватает сена: нужно {HAY_PER_FEED}, есть {available}"
            )
        await self._farm.consume_hay(telegram_user_id, HAY_PER_FEED)
        pet = await self._repository.feed(pet, datetime.now(timezone.utc))
        return _status(pet)

    async def revive(self, telegram_user_id: int) -> PetStatus:
        """ "Похоронить и завести нового" — единственный способ снять
        state="dead". Сбрасывает last_fed_at, но НЕ deaths_count — это
        и есть постоянная память о пренебрежении, честный счётчик, а не
        отмываемая статистика."""
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            raise NoPetError("Питомца ещё не было")
        if _status(pet).state != "dead":
            raise NotDeadError("Питомец жив, оживлять нечего")
        pet = await self._repository.revive(pet, datetime.now(timezone.utc))
        return _status(pet)


def _status(pet: Pet) -> PetStatus:
    last_fed = _as_aware(pet.last_fed_at)
    hours = (datetime.now(timezone.utc) - last_fed).total_seconds() / 3600

    # Голод и настроение — ДВЕ независимые линейные шкалы, не одна
    # производная от другой. Голод достигает потолка в HUNGER_FULL_HOURS
    # и дальше не растёт (питомец физически не может быть "голоднее
    # максимума") — если бы настроение считалось от уже упёршегося в 100
    # голода, разница между "голоден" и "болен" была бы не видна:
    # 100-100-штраф всё равно клампится в те же 0. Настроение вместо
    # этого падает своим темпом до самой смерти (DEATH_AFTER_HOURS) —
    # тогда "болен" читается как более низкое настроение, чем просто
    # "голоден", а не как тот же 0 с невидимым вычетом.
    hunger = round(_clamp(hours / HUNGER_FULL_HOURS * 100))
    mood = round(_clamp(100 - hours / DEATH_AFTER_HOURS * 100))

    if hours >= DEATH_AFTER_HOURS:
        state: PetState = "dead"
        next_threshold_at = None
    elif hours >= SICK_AFTER_HOURS:
        state = "sick"
        next_threshold_at = last_fed + timedelta(hours=DEATH_AFTER_HOURS)
    elif hours >= HUNGER_FULL_HOURS:
        state = "hungry"
        next_threshold_at = last_fed + timedelta(hours=SICK_AFTER_HOURS)
    else:
        state = "healthy"
        next_threshold_at = last_fed + timedelta(hours=HUNGER_FULL_HOURS)

    return PetStatus(
        exists=True,
        hunger=hunger,
        mood=mood,
        state=state,
        last_fed_at=pet.last_fed_at,
        deaths_count=pet.deaths_count,
        next_threshold_at=next_threshold_at,
    )


def _as_aware(value: datetime) -> datetime:
    """SQLite не хранит tzinfo (см. HANDOFF.md, «Технические нюансы»,
    п.3) — тот же приём, что в app/farm/service.py и app/farm/repository.py."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return min(hi, max(lo, value))
