"""
ShopService — покупка за монеты (specs/028, фаза 1).

Заработок монет подменён заглушкой: сколько именно даёт чек-ин — забота
RewardsService и его собственных тестов (tests/rewards/), здесь
проверяется только вычитание, инвентарь и запреты.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.rewards.service import RewardsStatus
from app.shop.repository import ShopRepository
from app.shop.service import (
    AlreadyOwnedError,
    InsufficientCoinsError,
    ShopService,
    UnknownItemError,
)

# Цены из каталога, зафиксированные здесь ЯВНО: тест должен упасть, если
# цену поменяли, не подумав о балансе экономики.
CLOVER = "seed_clover"
CLOVER_PRICE = 30
HAT = "decor_hat"
HAT_PRICE = 60


class FakeRewardsService:
    """Столько монет заработано визитами — остальные поля статуса
    магазину не нужны."""

    def __init__(self, total_coins: int) -> None:
        self._total = total_coins

    async def get_status(self, telegram_user_id: int) -> RewardsStatus:
        return RewardsStatus(
            claimed_today=True,
            streak=1,
            total_coins=self._total,
            coins_today=0,
            lucky_today=False,
        )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


def build(session, earned: int) -> ShopService:
    return ShopService(ShopRepository(session), FakeRewardsService(earned))


async def test_balance_equals_earned_without_purchases(session):
    state = await build(session, 100).get_state(1)

    assert state.earned_coins == 100
    assert state.spent_coins == 0
    assert state.balance == 100


async def test_purchase_subtracts_price_from_balance(session):
    service = build(session, 100)

    state = await service.purchase(1, CLOVER)

    assert state.balance == 100 - CLOVER_PRICE
    assert state.spent_coins == CLOVER_PRICE


async def test_purchase_survives_reload(session):
    """Баланс не живёт в памяти сервиса — он выводится из истории, и
    новый экземпляр сервиса видит ту же трату."""
    await build(session, 100).purchase(1, CLOVER)

    state = await build(session, 100).get_state(1)

    assert state.balance == 100 - CLOVER_PRICE


async def test_purchase_does_not_touch_earned_coins(session):
    """Ключевое свойство варианта (A): заработанное за всё время не
    уменьшается — на нём висят звания, достижения и открытые темы /ui,
    покупка не должна их отбирать."""
    service = build(session, 100)

    state = await service.purchase(1, CLOVER)

    assert state.earned_coins == 100


async def test_purchase_records_item_in_inventory(session):
    service = build(session, 100)

    state = await service.purchase(1, CLOVER)

    owned = {entry.item.id: entry.owned for entry in state.items}
    assert owned[CLOVER] == 1


async def test_repeatable_item_can_be_bought_twice(session):
    service = build(session, 100)
    await service.purchase(1, CLOVER)

    state = await service.purchase(1, CLOVER)

    owned = {entry.item.id: entry.owned for entry in state.items}
    assert owned[CLOVER] == 2
    assert state.balance == 100 - 2 * CLOVER_PRICE


async def test_decoration_cannot_be_bought_twice(session):
    service = build(session, 500)
    await service.purchase(1, HAT)

    with pytest.raises(AlreadyOwnedError):
        await service.purchase(1, HAT)


async def test_already_owned_decoration_is_not_affordable(session):
    """Кнопка «Купить» на фронте гаснет по affordable — у купленного
    украшения оно False при любом балансе."""
    service = build(session, 500)

    state = await service.purchase(1, HAT)

    hat = next(entry for entry in state.items if entry.item.id == HAT)
    assert hat.affordable is False


async def test_purchase_without_enough_coins_raises(session):
    service = build(session, CLOVER_PRICE - 1)

    with pytest.raises(InsufficientCoinsError):
        await service.purchase(1, CLOVER)


async def test_failed_purchase_leaves_balance_untouched(session):
    service = build(session, CLOVER_PRICE - 1)

    with pytest.raises(InsufficientCoinsError):
        await service.purchase(1, CLOVER)

    assert (await service.get_state(1)).balance == CLOVER_PRICE - 1


async def test_purchase_with_exact_balance_is_allowed(session):
    """Ровно хватает — покупка проходит и баланс уходит в ноль, а не
    отклоняется как «недостаточно»."""
    service = build(session, CLOVER_PRICE)

    state = await service.purchase(1, CLOVER)

    assert state.balance == 0


async def test_unknown_item_raises(session):
    service = build(session, 100)

    with pytest.raises(UnknownItemError):
        await service.purchase(1, "no_such_item")


async def test_purchases_isolated_per_user(session):
    await build(session, 100).purchase(1, CLOVER)

    state = await build(session, 100).get_state(2)

    assert state.balance == 100
    assert all(entry.owned == 0 for entry in state.items)


async def test_affordable_reflects_balance(session):
    service = build(session, HAT_PRICE)

    state = await service.get_state(1)

    by_id = {entry.item.id: entry for entry in state.items}
    assert by_id[HAT].affordable is True
    assert by_id["decor_crown"].affordable is False
