"""
FarmService — покупка семян уже проверена в tests/shop/, здесь только
рост/посадка/сбор/полив/сено (specs/028, фаза 2).

ShopRepository подменена фейком: сколько куплено — забота
tests/shop/, здесь важно только то, что делает с этими числами ферма.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.farm.repository import FarmRepository
from app.farm.service import (
    FERTILIZER_GROW_HOURS,
    GROW_HOURS,
    HAY_PER_PLOT,
    RAIN_REDUCE_HOURS,
    FarmService,
    NoBoosterError,
    NoSeedsError,
    PlotNotFoundError,
    PlotNotReadyError,
)


class FakeShopRepository:
    """Столько куплено каждого товара для ПОЛЬЗОВАТЕЛЯ 1 — остальные
    видят пустой магазин, так же как настоящий ShopRepository фильтрует
    по telegram_user_id."""

    def __init__(self, purchased: dict[str, int]) -> None:
        self._purchased = purchased

    async def purchased_counts(self, telegram_user_id: int) -> dict[str, int]:
        return dict(self._purchased) if telegram_user_id == 1 else {}


def _naive(value: datetime) -> datetime:
    """SQLAlchemy может вернуть тот же закешированный (aware) объект или
    заново прочитанный из SQLite (naive) — сравнение приводит обе стороны
    к одному виду (см. tests/farm/test_repository.py)."""
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


def build(session, **purchased) -> FarmService:
    return FarmService(FarmRepository(session), FakeShopRepository(purchased))


async def test_state_without_purchases_is_empty(session):
    state = await build(session).get_state(1)

    assert state.available_seeds == 0
    assert state.available_fertilizer == 0
    assert state.available_rain == 0
    assert state.available_hay == 0
    assert state.plots == []


async def test_plant_without_seeds_raises(session):
    service = build(session)

    with pytest.raises(NoSeedsError):
        await service.plant(1)


async def test_plant_consumes_one_seed(session):
    service = build(session, seed_clover=2)

    state = await service.plant(1)

    assert state.available_seeds == 1
    assert len(state.plots) == 1


async def test_planted_plot_ready_after_grow_hours(session):
    service = build(session, seed_clover=1)

    state = await service.plant(1)

    plot = state.plots[0]
    assert plot.ready is False
    expected = plot.planted_at + timedelta(hours=GROW_HOURS)
    assert abs((plot.ready_at - expected).total_seconds()) < 1
    assert plot.hay_yield == HAY_PER_PLOT
    assert plot.fertilized is False


async def test_plant_with_fertilizer_without_booster_raises(session):
    service = build(session, seed_clover=1)

    with pytest.raises(NoBoosterError):
        await service.plant(1, use_fertilizer=True)

    # Семя не должно списаться при отказе на более позднем шаге проверки.
    state = await service.get_state(1)
    assert state.available_seeds == 1
    assert state.plots == []


async def test_plant_with_fertilizer_halves_grow_time(session):
    service = build(session, seed_clover=1, booster_fertilizer=1)

    state = await service.plant(1, use_fertilizer=True)

    plot = state.plots[0]
    assert plot.fertilized is True
    expected = plot.planted_at + timedelta(hours=FERTILIZER_GROW_HOURS)
    assert abs((plot.ready_at - expected).total_seconds()) < 1
    assert state.available_fertilizer == 0
    assert state.available_seeds == 0


async def test_harvest_unknown_plot_raises(session):
    service = build(session)

    with pytest.raises(PlotNotFoundError):
        await service.harvest(1, 999)


async def test_harvest_before_ready_raises(session):
    service = build(session, seed_clover=1)
    state = await service.plant(1)
    plot_id = state.plots[0].id

    with pytest.raises(PlotNotReadyError):
        await service.harvest(1, plot_id)


async def test_harvest_other_users_plot_raises_not_found(session):
    service = build(session, seed_clover=1)
    state = await service.plant(1)
    plot_id = state.plots[0].id

    with pytest.raises(PlotNotFoundError):
        await service.harvest(2, plot_id)


async def _force_ready(session, plot_id: int) -> None:
    """Грядка растёт сутки — тесты не ждут, а напрямую двигают ready_at
    в прошлое через тот же репозиторий, которым пользуется сервис."""
    repo = FarmRepository(session)
    plot = await repo.get_plot(plot_id)
    plot.ready_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await session.commit()


async def test_harvest_ready_plot_adds_hay_and_removes_from_active(session):
    service = build(session, seed_clover=1)
    state = await service.plant(1)
    plot_id = state.plots[0].id
    await _force_ready(session, plot_id)

    state = await service.harvest(1, plot_id)

    assert state.available_hay == HAY_PER_PLOT
    assert state.plots == []


async def test_harvest_twice_raises_second_time(session):
    service = build(session, seed_clover=1)
    state = await service.plant(1)
    plot_id = state.plots[0].id
    await _force_ready(session, plot_id)
    await service.harvest(1, plot_id)

    with pytest.raises(PlotNotFoundError):
        await service.harvest(1, plot_id)


async def test_apply_rain_without_booster_raises(session):
    service = build(session, seed_clover=1)
    await service.plant(1)

    with pytest.raises(NoBoosterError):
        await service.apply_rain(1)


async def test_apply_rain_reduces_ready_at_on_all_active_plots(session):
    service = build(session, seed_clover=2, booster_rain=1)
    await service.plant(1)
    state_before = await service.plant(1)

    state = await service.apply_rain(1)

    assert state.available_rain == 0
    for before, after in zip(state_before.plots, state.plots, strict=True):
        expected = _naive(before.ready_at) - timedelta(hours=RAIN_REDUCE_HOURS)
        assert abs((_naive(after.ready_at) - expected).total_seconds()) < 1


async def test_farm_state_isolated_per_user(session):
    service = build(session, seed_clover=1)
    await service.plant(1)

    state = await service.get_state(2)

    assert state.available_seeds == 0
    assert state.plots == []


async def test_consume_hay_reduces_available_hay(session):
    service = build(session, seed_clover=1)
    state = await service.plant(1)
    plot_id = state.plots[0].id
    await _force_ready(session, plot_id)
    await service.harvest(1, plot_id)

    remaining = await service.consume_hay(1, 5)

    assert remaining == HAY_PER_PLOT - 5
    assert await service.available_hay(1) == HAY_PER_PLOT - 5
