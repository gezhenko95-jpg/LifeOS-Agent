"""
PetService — голод/настроение/состояние как чистая функция от
last_fed_at, плюс переходы через feed/revive/adopt (specs/028, фаза 3).

FarmService подменена фейком: сколько сена доступно/потрачено — забота
tests/farm/, здесь важно только то, что делает с этими числами питомец.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.farm.service import InsufficientHayError
from app.pet.repository import PetRepository
from app.pet.service import (
    DEATH_AFTER_HOURS,
    HAY_PER_FEED,
    HUNGER_FULL_HOURS,
    SICK_AFTER_HOURS,
    AlreadyHasPetError,
    NoPetError,
    NotDeadError,
    PetIsDeadError,
    PetService,
)


class FakeFarmService:
    def __init__(self, hay: int = 100) -> None:
        self.hay = hay
        self.consumed = 0

    async def available_hay(self, telegram_user_id: int) -> int:
        return self.hay

    async def consume_hay(self, telegram_user_id: int, amount: int) -> int:
        self.hay -= amount
        self.consumed += amount
        return self.hay


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


def build(session, hay: int = 100):
    farm = FakeFarmService(hay)
    return PetService(PetRepository(session), farm), farm


async def _create_with_last_fed(session, hours_ago: float, user_id: int = 1) -> None:
    """Заводит питомца и сразу двигает last_fed_at в прошлое — тесты не
    ждут реального времени, состояние читается чистой функцией."""
    repo = PetRepository(session)
    pet = await repo.create(user_id, datetime.now(timezone.utc))
    pet.last_fed_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    await session.commit()


async def test_status_without_pet(session):
    service, _ = build(session)

    status = await service.get_status(1)

    assert status.exists is False
    assert status.state is None


async def test_adopt_creates_pet_at_full_health(session):
    service, _ = build(session)

    status = await service.adopt(1)

    assert status.exists is True
    assert status.state == "healthy"
    assert status.hunger == 0
    assert status.mood == 100
    assert status.deaths_count == 0
    assert status.next_threshold_at is not None


async def test_adopt_twice_raises(session):
    service, _ = build(session)
    await service.adopt(1)

    with pytest.raises(AlreadyHasPetError):
        await service.adopt(1)


async def test_freshly_fed_pet_is_healthy(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=1)

    status = await service.get_status(1)

    assert status.state == "healthy"
    assert 0 <= status.hunger < 10


async def test_hunger_grows_linearly_with_time(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS / 2)

    status = await service.get_status(1)

    assert status.state == "healthy"
    assert 45 <= status.hunger <= 55


async def test_pet_becomes_hungry_at_full_hunger_threshold(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS + 1)

    status = await service.get_status(1)

    assert status.state == "hungry"
    assert status.hunger == 100


async def test_pet_becomes_sick_after_threshold(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=SICK_AFTER_HOURS + 1)

    status = await service.get_status(1)

    assert status.state == "sick"
    assert status.hunger == 100  # голод уже упёрся в потолок...
    assert 0 < status.mood < 50  # ...но настроение продолжает падать своим темпом


async def test_mood_keeps_falling_through_hungry_and_sick_distinctly(session):
    """Ключевое свойство формулы (см. комментарий в _status): "голоден" и
    "болен" должны различаться настроением, а не оба клэмпиться в один и
    тот же 0 поверх уже максимального голода."""
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS + 1, user_id=1)
    hungry_mood = (await service.get_status(1)).mood

    await _create_with_last_fed(session, hours_ago=SICK_AFTER_HOURS + 1, user_id=2)
    sick_mood = (await service.get_status(2)).mood

    assert sick_mood < hungry_mood


async def test_pet_dies_after_death_threshold(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=DEATH_AFTER_HOURS + 1)

    status = await service.get_status(1)

    assert status.state == "dead"
    assert status.mood == 0
    assert status.next_threshold_at is None


async def test_feed_without_pet_raises(session):
    service, _ = build(session)

    with pytest.raises(NoPetError):
        await service.feed(1)


async def test_feed_resets_hunger_and_consumes_hay(session):
    service, farm = build(session, hay=100)
    await service.adopt(1)
    # Состарим питомца искусственно, минуя adopt (adopt всегда "сейчас").
    repo = PetRepository(session)
    pet = await repo.get(1)
    pet.last_fed_at = datetime.now(timezone.utc) - timedelta(hours=30)
    await session.commit()

    status = await service.feed(1)

    assert status.hunger == 0
    assert status.state == "healthy"
    assert farm.consumed == HAY_PER_FEED


async def test_feed_without_enough_hay_raises(session):
    service, _ = build(session, hay=HAY_PER_FEED - 1)
    await service.adopt(1)

    with pytest.raises(InsufficientHayError):
        await service.feed(1)


async def test_feed_dead_pet_raises_and_does_not_consume_hay(session):
    service, farm = build(session, hay=100)
    await _create_with_last_fed(session, hours_ago=DEATH_AFTER_HOURS + 1)

    with pytest.raises(PetIsDeadError):
        await service.feed(1)

    assert farm.consumed == 0


async def test_revive_alive_pet_raises(session):
    service, _ = build(session)
    await service.adopt(1)

    with pytest.raises(NotDeadError):
        await service.revive(1)


async def test_revive_without_pet_raises(session):
    service, _ = build(session)

    with pytest.raises(NoPetError):
        await service.revive(1)


async def test_revive_dead_pet_resets_state_but_keeps_deaths_count(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=DEATH_AFTER_HOURS + 1)

    status = await service.revive(1)

    assert status.state == "healthy"
    assert status.hunger == 0
    assert status.deaths_count == 1


async def test_second_death_increments_counter_again(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=DEATH_AFTER_HOURS + 1)
    await service.revive(1)
    repo = PetRepository(session)
    pet = await repo.get(1)
    pet.last_fed_at = datetime.now(timezone.utc) - timedelta(
        hours=DEATH_AFTER_HOURS + 1
    )
    await session.commit()

    status = await service.revive(1)

    assert status.deaths_count == 2


async def test_pet_status_isolated_per_user(session):
    service, _ = build(session)
    await service.adopt(1)

    status = await service.get_status(2)

    assert status.exists is False


async def test_list_due_hunger_notifications_excludes_healthy_pet(session):
    service, _ = build(session)
    await service.adopt(1)

    due = await service.list_due_hunger_notifications()

    assert due == []


async def test_list_due_hunger_notifications_includes_hungry_unnotified_pet(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS + 1, user_id=1)

    due = await service.list_due_hunger_notifications()

    assert [p.telegram_user_id for p in due] == [1]


async def test_mark_hunger_notified_removes_pet_from_due_list(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS + 1, user_id=1)
    repo = PetRepository(session)
    pet = await repo.get(1)

    await service.mark_hunger_notified(pet)

    assert await service.list_due_hunger_notifications() == []


async def test_feeding_after_notification_makes_pet_due_again_next_episode(session):
    """Ключевое свойство dedup: hungry_notified_at НЕ сбрасывается явно
    при кормлении (см. докстринг Pet.hungry_notified_at) — джоба
    отличает старый эпизод от нового сравнением с last_fed_at, а не
    флагом "уведомлён/нет".

    Оба поля выставлены напрямую через репозиторий (не через
    service.mark_hunger_notified/feed, которые оба берут "сейчас" в
    момент вызова — тест выполняется за миллисекунды и не может
    развести события по часам через реальные вызовы). Хронология: было
    старое уведомление (100ч назад), ПОСЛЕ него было кормление (55ч
    назад — позже уведомления, но уже снова достаточно давно, чтобы
    питомец успел проголодать заново)."""
    service, _ = build(session)
    repo = PetRepository(session)
    now = datetime.now(timezone.utc)
    pet = await repo.create(1, now - timedelta(hours=100))
    await repo.mark_hungry_notified(pet, now - timedelta(hours=100))
    pet = await repo.get(1)
    pet.last_fed_at = now - timedelta(hours=55)
    await session.commit()

    due = await service.list_due_hunger_notifications()

    assert [p.telegram_user_id for p in due] == [1]


async def test_dead_pet_is_included_in_hunger_notifications(session):
    """ "Голоден или хуже" — фаза 3 не различает hungry/sick/dead
    отдельными уведомлениями, одно сообщение на весь неблагополучный
    диапазон (см. app/pet/service.py::list_due_hunger_notifications)."""
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=DEATH_AFTER_HOURS + 1, user_id=1)

    due = await service.list_due_hunger_notifications()

    assert [p.telegram_user_id for p in due] == [1]


async def test_notifications_isolated_per_user(session):
    service, _ = build(session)
    await _create_with_last_fed(session, hours_ago=HUNGER_FULL_HOURS + 1, user_id=1)
    await service.adopt(2)

    due = await service.list_due_hunger_notifications()

    assert [p.telegram_user_id for p in due] == [1]
