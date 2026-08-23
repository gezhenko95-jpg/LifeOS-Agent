"""
ContactRepository — против настоящей SQLite.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.models import Contact
from app.crm.repository import ContactRepository
from app.db.base import Base

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


async def _add(session, **kwargs) -> Contact:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("name", "Аня")
    kwargs.setdefault("last_contact_at", NOW)
    contact = Contact(**kwargs)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def test_list_by_user_orders_stale_first(session):
    repo = ContactRepository(session)
    recent = await _add(session, name="Recent", last_contact_at=NOW - timedelta(days=1))
    stale = await _add(session, name="Stale", last_contact_at=NOW - timedelta(days=40))

    result = await repo.list_by_user(1)

    assert result == [stale, recent]


async def test_list_by_user_filters_by_owner(session):
    repo = ContactRepository(session)
    await _add(session, telegram_user_id=2)
    mine = await _add(session, telegram_user_id=1)

    result = await repo.list_by_user(1)

    assert result == [mine]


async def test_add_persists_birthday(session):
    repo = ContactRepository(session)
    contact = await repo.add(
        Contact(
            telegram_user_id=1,
            name="Петя",
            birthday_month=9,
            birthday_day=14,
            last_contact_at=NOW,
        )
    )

    assert (contact.birthday_month, contact.birthday_day) == (9, 14)


async def test_delete_removes_contact(session):
    repo = ContactRepository(session)
    contact = await _add(session)

    await repo.delete(contact)

    assert await repo.get_by_id(contact.id) is None
