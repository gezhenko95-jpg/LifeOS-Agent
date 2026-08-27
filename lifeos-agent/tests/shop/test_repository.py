"""
ShopRepository — против настоящей SQLite (по образцу
tests/rewards/test_repository.py).
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.shop.models import PURCHASE
from app.shop.repository import ShopRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def test_net_amount_is_zero_without_transactions(session):
    repo = ShopRepository(session)

    assert await repo.net_amount(1) == 0


async def test_net_amount_sums_with_sign(session):
    repo = ShopRepository(session)
    await repo.add_transaction(1, -30, PURCHASE, "seed_clover")
    await repo.add_transaction(1, -25, PURCHASE, "booster_rain")

    assert await repo.net_amount(1) == -55


async def test_transactions_isolated_per_user(session):
    repo = ShopRepository(session)
    await repo.add_transaction(1, -30, PURCHASE, "seed_clover")

    assert await repo.net_amount(2) == 0
    assert await repo.purchased_counts(2) == {}


async def test_purchased_counts_groups_by_item(session):
    repo = ShopRepository(session)
    await repo.add_transaction(1, -30, PURCHASE, "seed_clover")
    await repo.add_transaction(1, -30, PURCHASE, "seed_clover")
    await repo.add_transaction(1, -60, PURCHASE, "decor_hat")

    assert await repo.purchased_counts(1) == {"seed_clover": 2, "decor_hat": 1}


async def test_purchased_counts_ignores_non_purchases(session):
    """Начисление мимо чек-ина (amount > 0, без товара) — движение монет,
    но не покупка: в инвентарь попадать не должно."""
    repo = ShopRepository(session)
    await repo.add_transaction(1, 100, "bonus", None)
    await repo.add_transaction(1, -30, PURCHASE, "seed_clover")

    assert await repo.purchased_counts(1) == {"seed_clover": 1}
    assert await repo.net_amount(1) == 70
