"""
MoodService — repository замокан.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.mood.models import MoodEntry
from app.mood.service import MoodService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda e: e
    return repo


def _entry(**kwargs) -> MoodEntry:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("score", 3)
    kwargs.setdefault("logged_at", NOW)
    return MoodEntry(**kwargs)


async def test_log_mood_persists_score(repository):
    service = MoodService(repository)

    entry = await service.log_mood(1, 4)

    assert entry.score == 4
    repository.add.assert_awaited_once()


async def test_log_mood_rejects_out_of_range_score(repository):
    service = MoodService(repository)

    with pytest.raises(ValueError):
        await service.log_mood(1, 0)
    with pytest.raises(ValueError):
        await service.log_mood(1, 6)


async def test_log_mood_empty_note_becomes_none(repository):
    service = MoodService(repository)

    entry = await service.log_mood(1, 3, note="   ")

    assert entry.note is None


async def test_delete_entry_owned(repository):
    entry = _entry(id=5)
    repository.get_by_id.return_value = entry
    service = MoodService(repository)

    result = await service.delete_entry(1, 5)

    assert result is entry
    repository.delete.assert_awaited_once_with(entry)


async def test_delete_entry_wrong_owner_returns_none(repository):
    entry = _entry(id=5, telegram_user_id=2)
    repository.get_by_id.return_value = entry
    service = MoodService(repository)

    result = await service.delete_entry(1, 5)

    assert result is None
    repository.delete.assert_not_awaited()


async def test_delete_entry_missing_returns_none(repository):
    repository.get_by_id.return_value = None
    service = MoodService(repository)

    result = await service.delete_entry(1, 999)

    assert result is None


async def test_list_recent_delegates_to_repository(repository):
    repository.list_recent.return_value = [_entry()]
    service = MoodService(repository)

    result = await service.list_recent(1, limit=5)

    assert len(result) == 1
    repository.list_recent.assert_awaited_once_with(1, 5)
