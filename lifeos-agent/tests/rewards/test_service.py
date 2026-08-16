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


@pytest.fixture(autouse=True)
def no_luck(monkeypatch):
    """Удача тестируется отдельно (test_claim_today_lucky_day_doubles_coins
    и test_claim_today_hides_luck_before_claiming) — здесь она мешала бы
    проверять базовую логику стрика/идемпотентности (см. tests/rewards/
    test_coins.py про источник флейковости)."""
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: False)


async def test_claim_today_first_time_adds_checkin(repository):
    repository.has_checkin_on.return_value = False
    repository.list_days.return_value = {TODAY}
    service = RewardsService(repository)

    status = await service.claim_today(1)

    repository.add_checkin.assert_awaited_once_with(1, TODAY)
    assert status.claimed_today is True
    assert status.streak == 1
    assert status.total_coins == 12
    assert status.coins_today == 12
    assert status.lucky_today is False


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
    # Ничего не забрано сегодня — и монет за сегодня ещё нет.
    assert status.coins_today == 0


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


async def test_claim_today_lucky_day_doubles_coins(repository, monkeypatch):
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: True)
    repository.has_checkin_on.return_value = False
    repository.list_days.return_value = {TODAY}
    service = RewardsService(repository)

    status = await service.claim_today(1)

    assert status.lucky_today is True
    assert status.coins_today == 24  # 12 * 2
    assert status.total_coins == 24


async def test_status_hides_luck_before_claiming(repository, monkeypatch):
    """Удача не раскрывается, пока день не забран — иначе клик по
    "Забрать" терял бы элемент сюрприза."""
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: True)
    repository.list_days.return_value = {TODAY - timedelta(days=1)}
    service = RewardsService(repository)

    status = await service.get_status(1)

    assert status.claimed_today is False
    assert status.lucky_today is False
