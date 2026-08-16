"""
RewardsRepository — против настоящей SQLite.
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.rewards.repository import RewardsRepository

TODAY = date.today()


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def test_has_checkin_on_false_when_no_record(session):
    repo = RewardsRepository(session)

    assert await repo.has_checkin_on(1, TODAY) is False


async def test_add_checkin_then_has_checkin_on_true(session):
    repo = RewardsRepository(session)
    await repo.add_checkin(1, TODAY)

    assert await repo.has_checkin_on(1, TODAY) is True


async def test_checkins_isolated_per_user(session):
    repo = RewardsRepository(session)
    await repo.add_checkin(1, TODAY)

    assert await repo.has_checkin_on(2, TODAY) is False


async def test_list_days_returns_all_checked_dates(session):
    repo = RewardsRepository(session)
    await repo.add_checkin(1, TODAY)
    await repo.add_checkin(1, TODAY - timedelta(days=1))

    days = await repo.list_days(1)

    assert days == {TODAY, TODAY - timedelta(days=1)}


async def test_duplicate_checkin_same_day_violates_unique_constraint(session):
    """Уникальность (telegram_user_id, checked_on) не даёт задвоить
    награду за один день, даже если сервисный слой ошибётся."""
    repo = RewardsRepository(session)
    await repo.add_checkin(1, TODAY)

    with pytest.raises(IntegrityError):
        await repo.add_checkin(1, TODAY)
