"""
RewardsService — repository замокан.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from app.rewards.service import RewardsService

TODAY = date.today()


@pytest.fixture
def repository():
    return AsyncMock()


async def test_claim_today_first_time_adds_checkin(repository):
    repository.has_checkin_on.return_value = False
    repository.list_days.return_value = {TODAY}
    service = RewardsService(repository)

    status = await service.claim_today(1)

    repository.add_checkin.assert_awaited_once_with(1, TODAY)
    assert status.claimed_today is True
    assert status.streak == 1
    assert status.total_coins == 12


async def test_claim_today_is_idempotent(repository):
    """Повторный клик "забрать" в тот же день не должен давать монет
    дважды."""
    repository.has_checkin_on.return_value = True
    repository.list_days.return_value = {TODAY}
    service = RewardsService(repository)

    status = await service.claim_today(1)

    repository.add_checkin.assert_not_awaited()
    assert status.claimed_today is True


async def test_get_status_without_claiming_does_not_add_checkin(repository):
    repository.list_days.return_value = {TODAY - timedelta(days=1)}
    service = RewardsService(repository)

    status = await service.get_status(1)

    repository.add_checkin.assert_not_awaited()
    assert status.claimed_today is False
    # Стрик считается от вчера (сегодня ещё не отмечено), как у привычек.
    assert status.streak == 1


async def test_status_reflects_growing_streak(repository):
    repository.list_days.return_value = {
        TODAY,
        TODAY - timedelta(days=1),
        TODAY - timedelta(days=2),
    }
    service = RewardsService(repository)

    status = await service.get_status(1)

    assert status.streak == 3
    assert status.total_coins == 12 + 14 + 16
