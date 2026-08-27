"""
FarmRepository — против настоящей SQLite (по образцу
tests/rewards/test_repository.py).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.farm.models import FarmPlot
from app.farm.repository import FarmRepository

NOW = datetime.now(timezone.utc)


def _naive(value):
    """SQLAlchemy может вернуть тот же закешированный в identity map
    объект (ещё aware) или заново прочитанный из SQLite (уже naive) —
    сравнение по датам приводит обе стороны к одному виду."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


def make_plot(user_id=1, ready_delta_hours=24, harvested=False, hay=10):
    return FarmPlot(
        telegram_user_id=user_id,
        planted_at=NOW,
        ready_at=NOW + timedelta(hours=ready_delta_hours),
        fertilized=False,
        hay_yield=hay,
        harvested_at=NOW if harvested else None,
    )


async def test_add_plot_and_get_plot(session):
    repo = FarmRepository(session)
    plot = await repo.add_plot(make_plot())

    fetched = await repo.get_plot(plot.id)

    assert fetched is not None
    assert fetched.telegram_user_id == 1


async def test_get_own_plot_returns_none_for_other_owner(session):
    repo = FarmRepository(session)
    plot = await repo.add_plot(make_plot(user_id=1))

    assert await repo.get_own_plot(2, plot.id) is None
    assert await repo.get_own_plot(1, plot.id) is not None


async def test_list_active_plots_excludes_harvested(session):
    repo = FarmRepository(session)
    await repo.add_plot(make_plot(harvested=False))
    await repo.add_plot(make_plot(harvested=True))

    active = await repo.list_active_plots(1)

    assert len(active) == 1
    assert active[0].harvested_at is None


async def test_mark_harvested_sets_timestamp(session):
    # SQLite не хранит tzinfo — сравниваем naive-версией, тот же приём,
    # что и в остальных тестах на datetime из БД в этом проекте.
    repo = FarmRepository(session)
    plot = await repo.add_plot(make_plot())

    harvested = await repo.mark_harvested(plot, NOW)

    assert _naive(harvested.harvested_at) == _naive(NOW)


async def test_total_planted_counts_all_plots_regardless_of_state(session):
    repo = FarmRepository(session)
    await repo.add_plot(make_plot(harvested=False))
    await repo.add_plot(make_plot(harvested=True))

    assert await repo.total_planted(1) == 2


async def test_total_fertilized_counts_only_fertilized(session):
    repo = FarmRepository(session)
    fertilized = make_plot()
    fertilized.fertilized = True
    await repo.add_plot(fertilized)
    await repo.add_plot(make_plot())

    assert await repo.total_fertilized(1) == 1


async def test_total_harvested_hay_sums_only_harvested(session):
    repo = FarmRepository(session)
    await repo.add_plot(make_plot(harvested=True, hay=10))
    await repo.add_plot(make_plot(harvested=True, hay=10))
    await repo.add_plot(make_plot(harvested=False, hay=10))

    assert await repo.total_harvested_hay(1) == 20


async def test_push_ready_at_earlier_subtracts_hours_but_not_before_floor(session):
    repo = FarmRepository(session)
    soon = await repo.add_plot(make_plot(ready_delta_hours=2))
    far = await repo.add_plot(make_plot(ready_delta_hours=20))

    await repo.push_ready_at_earlier([soon, far], hours=6, floor=NOW)

    # soon: NOW+2h - 6h = NOW-4h -> floored at NOW
    assert _naive((await repo.get_plot(soon.id)).ready_at) == _naive(NOW)
    # far: NOW+20h - 6h = NOW+14h, above floor, kept as computed
    assert _naive((await repo.get_plot(far.id)).ready_at) == _naive(
        NOW + timedelta(hours=14)
    )


async def test_record_and_read_supply_use(session):
    repo = FarmRepository(session)
    await repo.record_supply_use(1, "seed_clover")
    await repo.record_supply_use(1, "seed_clover")
    await repo.record_supply_use(1, "booster_rain")

    counts = await repo.supply_used_counts(1)

    assert counts == {"seed_clover": 2, "booster_rain": 1}


async def test_supply_use_isolated_per_user(session):
    repo = FarmRepository(session)
    await repo.record_supply_use(1, "seed_clover")

    assert await repo.supply_used_counts(2) == {}


async def test_hay_consumption_round_trip(session):
    repo = FarmRepository(session)
    await repo.record_hay_consumption(1, 5)
    await repo.record_hay_consumption(1, 5)

    assert await repo.total_hay_consumed(1) == 10
    assert await repo.total_hay_consumed(2) == 0
