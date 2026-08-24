"""
DebtRepository — против настоящей SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.finance.models import Debt
from app.finance.repository import DebtRepository

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


async def _add(session, telegram_user_id=1, **kwargs) -> Debt:
    kwargs.setdefault("name", "Долг")
    kwargs.setdefault("total_amount", 1000)
    kwargs.setdefault("remaining_amount", 1000)
    debt = Debt(telegram_user_id=telegram_user_id, **kwargs)
    session.add(debt)
    await session.commit()
    await session.refresh(debt)
    return debt


async def test_list_by_user_orders_by_due_date_ascending(session):
    later = await _add(session, name="Позже", due_date=NOW + timedelta(days=30))
    sooner = await _add(session, name="Раньше", due_date=NOW + timedelta(days=3))

    debts = await DebtRepository(session).list_by_user(1)

    assert [d.id for d in debts] == [sooner.id, later.id]


async def test_list_by_user_puts_no_due_date_last(session):
    no_date = await _add(session, name="Без срока", due_date=None)
    with_date = await _add(session, name="Со сроком", due_date=NOW + timedelta(days=5))

    debts = await DebtRepository(session).list_by_user(1)

    assert [d.id for d in debts] == [with_date.id, no_date.id]


async def test_list_by_user_ignores_other_users(session):
    await _add(session, telegram_user_id=2, name="Чужой долг")

    debts = await DebtRepository(session).list_by_user(1)

    assert debts == []
