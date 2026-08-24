"""FocusSessionRepository — против настоящей SQLite."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.focus.models import CANCELLED, COMPLETED, IN_PROGRESS, ON_BREAK, FocusSession
from app.focus.repository import FocusSessionRepository

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


async def _add(session, telegram_user_id=1, **kwargs) -> FocusSession:
    kwargs.setdefault("work_minutes", 25)
    kwargs.setdefault("break_minutes", 5)
    kwargs.setdefault("started_at", NOW)
    kwargs.setdefault("work_ends_at", NOW + timedelta(minutes=25))
    kwargs.setdefault("status", IN_PROGRESS)
    focus = FocusSession(telegram_user_id=telegram_user_id, **kwargs)
    session.add(focus)
    await session.commit()
    await session.refresh(focus)
    return focus


async def test_get_active_finds_in_progress(session):
    active = await _add(session, status=IN_PROGRESS)

    found = await FocusSessionRepository(session).get_active(1)

    assert found.id == active.id


async def test_get_active_finds_on_break(session):
    active = await _add(session, status=ON_BREAK)

    found = await FocusSessionRepository(session).get_active(1)

    assert found.id == active.id


async def test_get_active_ignores_completed_and_cancelled(session):
    await _add(session, status=COMPLETED)
    await _add(session, status=CANCELLED)

    found = await FocusSessionRepository(session).get_active(1)

    assert found is None


async def test_get_active_ignores_other_users(session):
    await _add(session, telegram_user_id=2, status=IN_PROGRESS)

    found = await FocusSessionRepository(session).get_active(1)

    assert found is None


async def test_list_due_work_end(session):
    due = await _add(
        session, status=IN_PROGRESS, work_ends_at=NOW - timedelta(minutes=1)
    )
    await _add(session, status=IN_PROGRESS, work_ends_at=NOW + timedelta(minutes=10))

    results = await FocusSessionRepository(session).list_due_work_end(NOW)

    assert [s.id for s in results] == [due.id]


async def test_list_due_work_end_skips_already_notified(session):
    await _add(
        session,
        status=IN_PROGRESS,
        work_ends_at=NOW - timedelta(minutes=1),
        work_notified_at=NOW,
    )

    results = await FocusSessionRepository(session).list_due_work_end(NOW)

    assert results == []


async def test_list_due_break_end(session):
    due = await _add(
        session,
        status=ON_BREAK,
        break_ends_at=NOW - timedelta(minutes=1),
    )
    await _add(session, status=ON_BREAK, break_ends_at=NOW + timedelta(minutes=5))

    results = await FocusSessionRepository(session).list_due_break_end(NOW)

    assert [s.id for s in results] == [due.id]


async def test_stats_since_counts_completed_only(session):
    await _add(session, status=COMPLETED, work_minutes=25, started_at=NOW)
    await _add(session, status=COMPLETED, work_minutes=40, started_at=NOW)
    await _add(session, status=CANCELLED, work_minutes=25, started_at=NOW)

    count, minutes = await FocusSessionRepository(session).stats_since(
        1, NOW - timedelta(days=1)
    )

    assert count == 2
    assert minutes == 65


async def test_stats_since_excludes_before_period(session):
    await _add(
        session, status=COMPLETED, work_minutes=25, started_at=NOW - timedelta(days=30)
    )

    count, minutes = await FocusSessionRepository(session).stats_since(
        1, NOW - timedelta(days=7)
    )

    assert count == 0
    assert minutes == 0


async def test_stats_since_no_sessions_returns_zeros(session):
    count, minutes = await FocusSessionRepository(session).stats_since(
        1, NOW - timedelta(days=7)
    )

    assert count == 0
    assert minutes == 0
