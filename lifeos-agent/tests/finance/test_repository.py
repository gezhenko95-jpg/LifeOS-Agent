"""
FinanceRepository — против настоящей SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.finance.models import EXPENSE, INCOME, Transaction
from app.finance.repository import FinanceRepository

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add(session, **kwargs) -> Transaction:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("kind", EXPENSE)
    kwargs.setdefault("amount", 100)
    kwargs.setdefault("occurred_at", NOW)
    transaction = Transaction(**kwargs)
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction


async def test_list_since_filters_by_date(session):
    repo = FinanceRepository(session)
    await _add(session, occurred_at=NOW - timedelta(days=40))
    recent = await _add(session, occurred_at=NOW - timedelta(days=1))

    result = await repo.list_since(1, NOW - timedelta(days=10))

    assert result == [recent]


async def test_list_since_filters_by_user(session):
    repo = FinanceRepository(session)
    await _add(session, telegram_user_id=2)
    mine = await _add(session, telegram_user_id=1)

    result = await repo.list_since(1, NOW - timedelta(days=10))

    assert result == [mine]


async def test_list_since_orders_by_occurred_at(session):
    repo = FinanceRepository(session)
    later = await _add(session, occurred_at=NOW - timedelta(hours=1))
    earlier = await _add(session, occurred_at=NOW - timedelta(hours=5))

    result = await repo.list_since(1, NOW - timedelta(days=1))

    assert result == [earlier, later]


async def test_add_income_has_no_category(session):
    repo = FinanceRepository(session)
    transaction = await repo.add(
        Transaction(telegram_user_id=1, kind=INCOME, amount=80000, occurred_at=NOW)
    )

    assert transaction.category is None
