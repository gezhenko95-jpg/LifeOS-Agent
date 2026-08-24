"""DebtPaymentRepository — против настоящей SQLite."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.finance.models import Debt, DebtPayment
from app.finance.repository import DebtPaymentRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add_debt(session, telegram_user_id=1) -> Debt:
    debt = Debt(
        telegram_user_id=telegram_user_id,
        name="Долг",
        total_amount=1000,
        remaining_amount=1000,
    )
    session.add(debt)
    await session.commit()
    await session.refresh(debt)
    return debt


async def _add_payment(session, debt_id, amount) -> DebtPayment:
    payment = DebtPayment(debt_id=debt_id, amount=amount)
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def test_list_by_debt_orders_by_paid_at(session):
    debt = await _add_debt(session)
    first = await _add_payment(session, debt.id, 100)
    second = await _add_payment(session, debt.id, 200)

    payments = await DebtPaymentRepository(session).list_by_debt(debt.id)

    assert [p.id for p in payments] == [first.id, second.id]


async def test_list_by_debt_ignores_other_debts(session):
    debt1 = await _add_debt(session)
    debt2 = await _add_debt(session)
    await _add_payment(session, debt1.id, 100)

    payments = await DebtPaymentRepository(session).list_by_debt(debt2.id)

    assert payments == []
