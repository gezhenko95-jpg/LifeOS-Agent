"""FocusSessionService — repository замокан."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.focus.models import CANCELLED, COMPLETED, IN_PROGRESS, ON_BREAK, FocusSession
from app.focus.service import FocusSessionService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda s: s
    repo.save.side_effect = lambda s: s
    repo.get_active.return_value = None
    return repo


def _session(**kwargs) -> FocusSession:
    kwargs.setdefault("id", 1)
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("work_minutes", 25)
    kwargs.setdefault("break_minutes", 5)
    kwargs.setdefault("started_at", NOW)
    kwargs.setdefault("work_ends_at", NOW + timedelta(minutes=25))
    kwargs.setdefault("status", IN_PROGRESS)
    return FocusSession(**kwargs)


async def test_start_session_defaults(repository):
    service = FocusSessionService(repository)

    session = await service.start_session(1)

    assert session.work_minutes == 25
    assert session.break_minutes == 5
    assert session.status == IN_PROGRESS
    assert session.work_ends_at == session.started_at + timedelta(minutes=25)


async def test_start_session_custom_duration(repository):
    service = FocusSessionService(repository)

    session = await service.start_session(1, work_minutes=40, break_minutes=10)

    assert session.work_minutes == 40
    assert session.break_minutes == 10


async def test_start_session_with_task_id(repository):
    service = FocusSessionService(repository)

    session = await service.start_session(1, task_id=7)

    assert session.task_id == 7


async def test_start_session_non_positive_duration_raises(repository):
    service = FocusSessionService(repository)

    with pytest.raises(ValueError):
        await service.start_session(1, work_minutes=0)
    with pytest.raises(ValueError):
        await service.start_session(1, break_minutes=-5)


async def test_start_session_rejects_when_already_active(repository):
    repository.get_active.return_value = _session(status=IN_PROGRESS)
    service = FocusSessionService(repository)

    with pytest.raises(ValueError):
        await service.start_session(1)
    repository.add.assert_not_awaited()


async def test_get_active_session_delegates(repository):
    repository.get_active.return_value = _session()
    service = FocusSessionService(repository)

    result = await service.get_active_session(1)

    assert result is not None
    repository.get_active.assert_awaited_once_with(1)


async def test_cancel_session_in_progress(repository):
    session = _session(status=IN_PROGRESS)
    repository.get_by_id.return_value = session
    service = FocusSessionService(repository)

    cancelled = await service.cancel_session(1, 1)

    assert cancelled.status == CANCELLED


async def test_cancel_session_on_break(repository):
    session = _session(status=ON_BREAK)
    repository.get_by_id.return_value = session
    service = FocusSessionService(repository)

    cancelled = await service.cancel_session(1, 1)

    assert cancelled.status == CANCELLED


async def test_cancel_already_completed_returns_none(repository):
    session = _session(status=COMPLETED)
    repository.get_by_id.return_value = session
    service = FocusSessionService(repository)

    result = await service.cancel_session(1, 1)

    assert result is None
    repository.save.assert_not_awaited()


async def test_cancel_missing_session_returns_none(repository):
    repository.get_by_id.return_value = None
    service = FocusSessionService(repository)

    result = await service.cancel_session(1, 999)

    assert result is None


async def test_cancel_someone_elses_session_returns_none(repository):
    session = _session(status=IN_PROGRESS, telegram_user_id=2)
    repository.get_by_id.return_value = session
    service = FocusSessionService(repository)

    result = await service.cancel_session(1, 1)

    assert result is None


async def test_mark_work_notified_transitions_to_break(repository):
    session = _session(status=IN_PROGRESS, break_minutes=5)
    service = FocusSessionService(repository)

    updated = await service.mark_work_notified(session)

    assert updated.status == ON_BREAK
    assert updated.work_notified_at is not None
    assert updated.break_ends_at == session.work_ends_at + timedelta(minutes=5)


async def test_mark_break_notified_completes_session(repository):
    session = _session(status=ON_BREAK)
    service = FocusSessionService(repository)

    updated = await service.mark_break_notified(session)

    assert updated.status == COMPLETED
    assert updated.break_notified_at is not None


async def test_stats_since_delegates(repository):
    repository.stats_since.return_value = (3, 75)
    service = FocusSessionService(repository)

    count, minutes = await service.stats_since(1, NOW - timedelta(days=7))

    assert (count, minutes) == (3, 75)


async def test_list_due_work_end_delegates(repository):
    repository.list_due_work_end.return_value = [_session()]
    service = FocusSessionService(repository)

    result = await service.list_due_work_end(NOW)

    assert len(result) == 1
    repository.list_due_work_end.assert_awaited_once_with(NOW)


async def test_list_due_break_end_delegates(repository):
    repository.list_due_break_end.return_value = [_session()]
    service = FocusSessionService(repository)

    result = await service.list_due_break_end(NOW)

    assert len(result) == 1
    repository.list_due_break_end.assert_awaited_once_with(NOW)
