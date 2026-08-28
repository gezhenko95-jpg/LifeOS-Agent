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

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from app.farm.service import FarmService, InsufficientHayError
from app.pet.models import Pet
from app.pet.repository import PetRepository
from app.shop.catalog import DECOR, get_item
from app.shop.models import PET_ADVENTURE
from app.shop.repository import ShopRepository

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

# Приключения питомца (specs/030, по мотивам Finch). Настоящий random,
# не детерминированный хэш (как у coins.is_lucky_day) — событие разовое
# и сразу фиксируется в ledger, детерминизм там был нужен ИМЕННО для
# безопасного пересчёта total_coins заново на каждый запрос, здесь
# пересчёта нет.
ADVENTURE_BONUS_CHANCE = 0.4
ADVENTURE_BONUS_MIN_COINS = 3
ADVENTURE_BONUS_MAX_COINS = 10


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


class UnknownDecorationError(PetError):
    pass


class DecorationNotOwnedError(PetError):
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
    # Единственное поле статуса, которое НЕ производное — собственный
    # выбор владельца среди купленного в Магазине (см. docstring
    # Pet.equipped_decor_item_id).
    equipped_decor_item_id: str | None = None


@dataclass
class AdventureCandidate:
    """Готовое к отправке "приключение" (specs/030) — reward_coins уже
    решён (roll был сделан), запись в БД/начисление монет ещё нет: их
    делает record_adventure ПОСЛЕ того, как AI успешно сгенерировал
    текст (app/scheduler/pet_adventures.py) — неудачная попытка не
    должна сжигать сегодняшний день."""

    state: PetState
    reward_coins: int


class PetService:
    def __init__(
        self,
        repository: PetRepository,
        farm_service: FarmService,
        shop_repository: ShopRepository,
    ) -> None:
        self._repository = repository
        self._farm = farm_service
        self._shop = shop_repository

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

    async def equip(self, telegram_user_id: int, item_id: str | None) -> PetStatus:
        """Надеть украшение из Магазина или снять (item_id=None — снять
        всегда разрешено, владение не проверяется). Владение проверяется
        каждый раз заново по факту покупки (ShopRepository.purchased_
        counts), а не читается из отдельного "инвентаря питомца" — тот
        же принцип, что у остатков фермы: один источник правды, не два,
        которые могут разойтись."""
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            raise NoPetError("Сначала заведите питомца")

        if item_id is not None:
            item = get_item(item_id)
            if item is None or item.kind != DECOR:
                raise UnknownDecorationError(f"Нет такого украшения: {item_id}")
            owned = await self._shop.purchased_counts(telegram_user_id)
            if owned.get(item_id, 0) <= 0:
                raise DecorationNotOwnedError(f"«{item.title}» ещё не куплено")

        pet = await self._repository.set_equipped_decor(pet, item_id)
        return _status(pet)

    # --- Опрашивающая джоба (app/telegram/jobs.py::send_farm_pet_notifications_job) ---

    async def list_due_hunger_notifications(self) -> list[Pet]:
        """Питомцы не healthy (proголодался/болен/погиб), для которых
        текущий эпизод ещё не уведомлён. "Текущий эпизод" — не то же
        самое, что "hungry_notified_at is None": поле НЕ сбрасывается
        при кормлении (см. докстринг Pet.hungry_notified_at), поэтому
        условие "уже уведомляли" — hungry_notified_at позже последнего
        кормления. Голод — чистая функция времени (см. _status), её
        нельзя выразить в SQL-запросе репозитория, поэтому фильтрация
        здесь, после загрузки всех строк (проект single-user — одна
        строка на пользователя, нагрузка не проблема)."""
        due = []
        for pet in await self._repository.list_all():
            if _status(pet).state == "healthy":
                continue
            notified = pet.hungry_notified_at
            last_fed = _as_aware(pet.last_fed_at)
            if notified is not None and _as_aware(notified) >= last_fed:
                continue
            due.append(pet)
        return due

    async def mark_hunger_notified(self, pet: Pet) -> Pet:
        return await self._repository.mark_hungry_notified(
            pet, datetime.now(timezone.utc)
        )

    # --- Приключения (specs/030, по мотивам Finch; довесок к
    # send_evening_checkin_job, не отдельная джоба) ---------------------

    async def maybe_start_adventure(
        self, telegram_user_id: int
    ) -> Optional[AdventureCandidate]:
        """None — нет питомца/он мёртв, сегодня уже было приключение,
        или питомец сегодня не покормлен (триггер — покормлен, не
        отдельная проверка задач/привычек: PetService и так знает
        last_fed_at, кросс-доменная зависимость не нужна)."""
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            return None
        status = _status(pet)
        if status.state == "dead":
            return None

        today = datetime.now(timezone.utc).date()
        if pet.last_adventure_on == today:
            return None
        if _as_aware(pet.last_fed_at).date() != today:
            return None

        reward = 0
        if random.random() < ADVENTURE_BONUS_CHANCE:
            reward = random.randint(
                ADVENTURE_BONUS_MIN_COINS, ADVENTURE_BONUS_MAX_COINS
            )
        return AdventureCandidate(state=status.state, reward_coins=reward)

    async def record_adventure(self, telegram_user_id: int, reward_coins: int) -> None:
        """Вызывать ТОЛЬКО после успешной генерации текста приключения
        (app/scheduler/pet_adventures.py) — отметка "сегодня уже было"
        не должна сгорать впустую на ошибке AI (слот один в день, ретрая
        не будет до завтра)."""
        pet = await self._repository.get(telegram_user_id)
        if pet is None:
            return
        today = datetime.now(timezone.utc).date()
        await self._repository.mark_adventure(pet, today)
        if reward_coins > 0:
            await self._shop.add_transaction(
                telegram_user_id=telegram_user_id,
                amount=reward_coins,
                reason=PET_ADVENTURE,
            )


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
        equipped_decor_item_id=pet.equipped_decor_item_id,
    )


def _as_aware(value: datetime) -> datetime:
    """SQLite не хранит tzinfo (см. HANDOFF.md, «Технические нюансы»,
    п.3) — тот же приём, что в app/farm/service.py и app/farm/repository.py."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return min(hi, max(lo, value))
