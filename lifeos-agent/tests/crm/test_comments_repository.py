"""ContactCommentRepository — против настоящей SQLite."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.crm.models import Contact, ContactComment
from app.crm.repository import ContactCommentRepository
from app.db.base import Base
from tests.support import sqlite_engine


@pytest_asyncio.fixture
async def session():
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


async def _add_contact(session, telegram_user_id=1) -> Contact:
    contact = Contact(telegram_user_id=telegram_user_id, name="Аня")
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def _add_comment(session, contact_id, text, telegram_user_id=1) -> ContactComment:
    comment = ContactComment(
        contact_id=contact_id, telegram_user_id=telegram_user_id, text=text
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def test_list_by_contact_orders_by_created_at(session):
    contact = await _add_contact(session)
    first = await _add_comment(session, contact.id, "Первый")
    second = await _add_comment(session, contact.id, "Второй")

    comments = await ContactCommentRepository(session).list_by_contact(contact.id)

    assert [c.id for c in comments] == [first.id, second.id]


async def test_list_by_contact_ignores_other_contacts(session):
    contact1 = await _add_contact(session)
    contact2 = await _add_contact(session)
    await _add_comment(session, contact1.id, "Комментарий к контакту 1")

    comments = await ContactCommentRepository(session).list_by_contact(contact2.id)

    assert comments == []


async def test_count_by_contacts(session):
    contact1 = await _add_contact(session)
    contact2 = await _add_contact(session)
    await _add_comment(session, contact1.id, "1")
    await _add_comment(session, contact1.id, "2")
    await _add_comment(session, contact2.id, "3")

    counts = await ContactCommentRepository(session).count_by_contacts(
        [contact1.id, contact2.id]
    )

    assert counts == {contact1.id: 2, contact2.id: 1}


async def test_count_by_contacts_empty_list_returns_empty_dict(session):
    counts = await ContactCommentRepository(session).count_by_contacts([])

    assert counts == {}
