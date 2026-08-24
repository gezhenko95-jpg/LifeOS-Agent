"""
DebtService — repository замокан.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.finance.models import Debt
from app.finance.service import DebtService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda d: d
    repo.save.side_effect = lambda d: d
    return repo


def _debt(**kwargs) -> Debt:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("name", "Кредит на авто")
    kwargs.setdefault("total_amount", 100000)
    kwargs.setdefault("remaining_amount", 100000)
    return Debt(**kwargs)


async def test_add_debt_sets_remaining_equal_to_total(repository):
    service = DebtService(repository)

    debt = await service.add_debt(1, "Кредит на авто", 100000)

    assert debt.total_amount == 100000
    assert debt.remaining_amount == 100000


async def test_add_debt_strips_name(repository):
    service = DebtService(repository)

    debt = await service.add_debt(1, "  Кредит  ", 100000)

    assert debt.name == "Кредит"


async def test_add_debt_empty_name_raises(repository):
    service = DebtService(repository)

    with pytest.raises(ValueError):
        await service.add_debt(1, "   ", 100000)


async def test_add_debt_non_positive_amount_raises(repository):
    service = DebtService(repository)

    with pytest.raises(ValueError):
        await service.add_debt(1, "Кредит", 0)


async def test_record_payment_reduces_remaining(repository):
    debt = _debt(id=1, remaining_amount=100000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.record_payment(1, 1, 30000)

    assert updated.remaining_amount == 70000


async def test_record_payment_does_not_go_below_zero(repository):
    """Округление в большую сторону последним платежом закрывает долг,
    а не превращает Debt в "должны нам"."""
    debt = _debt(id=1, remaining_amount=10000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.record_payment(1, 1, 15000)

    assert updated.remaining_amount == 0


async def test_record_payment_non_positive_raises(repository):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    with pytest.raises(ValueError):
        await service.record_payment(1, 1, 0)


async def test_record_payment_missing_debt_returns_none(repository):
    repository.get_by_id.return_value = None
    service = DebtService(repository)

    result = await service.record_payment(1, 999, 1000)

    assert result is None


async def test_record_payment_wrong_owner_returns_none(repository):
    debt = _debt(id=1, telegram_user_id=2)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    result = await service.record_payment(1, 1, 1000)

    assert result is None
    repository.save.assert_not_awaited()


async def test_delete_debt(repository):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    deleted = await service.delete_debt(1, 1)

    assert deleted is debt
    repository.delete.assert_awaited_once_with(debt)


async def test_delete_debt_wrong_owner_returns_none(repository):
    debt = _debt(id=1, telegram_user_id=2)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    result = await service.delete_debt(1, 1)

    assert result is None
    repository.delete.assert_not_awaited()


async def test_list_debts_delegates_to_repository(repository):
    repository.list_by_user.return_value = [_debt()]
    service = DebtService(repository)

    result = await service.list_debts(1)

    assert len(result) == 1
    repository.list_by_user.assert_awaited_once_with(1)
