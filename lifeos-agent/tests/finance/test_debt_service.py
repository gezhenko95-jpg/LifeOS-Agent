"""
DebtService — repository замокан.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.finance.models import Debt, DebtPayment
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


# --- Лог платежей + план рассрочки (отчёт владельца 24.08, вечер #6, волна 7)


@pytest.fixture
def payment_repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda p: p
    return repo


async def test_record_payment_without_payment_repository_still_reduces_remaining(
    repository,
):
    """DebtService(repository) без второго аргумента — старый вызов,
    платёж по-прежнему проходит, просто без лога (см. __init__)."""
    debt = _debt(id=1, remaining_amount=100000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.record_payment(1, 1, 30000)

    assert updated.remaining_amount == 70000


async def test_record_payment_logs_to_payment_repository(
    repository, payment_repository
):
    debt = _debt(id=1, remaining_amount=100000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository, payment_repository)

    await service.record_payment(1, 1, 30000)

    payment_repository.add.assert_awaited_once()
    logged = payment_repository.add.await_args.args[0]
    assert logged.debt_id == 1
    assert logged.amount == 30000


async def test_list_payments_delegates_to_payment_repository(
    repository, payment_repository
):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    payment_repository.list_by_debt.return_value = [DebtPayment(debt_id=1, amount=5000)]
    service = DebtService(repository, payment_repository)

    payments = await service.list_payments(1, 1)

    assert len(payments) == 1
    payment_repository.list_by_debt.assert_awaited_once_with(1)


async def test_list_payments_wrong_owner_returns_empty(repository, payment_repository):
    debt = _debt(id=1, telegram_user_id=2)
    repository.get_by_id.return_value = debt
    service = DebtService(repository, payment_repository)

    payments = await service.list_payments(1, 1)

    assert payments == []
    payment_repository.list_by_debt.assert_not_awaited()


async def test_list_payments_without_payment_repository_returns_empty(repository):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    payments = await service.list_payments(1, 1)

    assert payments == []


async def test_update_debt_sets_monthly_payment(repository):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.update_debt(1, debt_id=1, monthly_payment=15000)

    assert updated.monthly_payment == 15000


async def test_update_debt_non_positive_monthly_payment_raises(repository):
    service = DebtService(repository)

    with pytest.raises(ValueError):
        await service.update_debt(1, debt_id=1, monthly_payment=0)


async def test_update_debt_clears_monthly_payment(repository):
    debt = _debt(id=1, monthly_payment=15000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.update_debt(1, debt_id=1, clear_monthly_payment=True)

    assert updated.monthly_payment is None


async def test_update_debt_sets_next_payment_due(repository):
    debt = _debt(id=1)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    updated = await service.update_debt(1, debt_id=1, next_payment_due=NOW)

    assert updated.next_payment_due == NOW


async def test_update_debt_missing_returns_none(repository):
    repository.get_by_id.return_value = None
    service = DebtService(repository)

    result = await service.update_debt(1, debt_id=999, monthly_payment=1000)

    assert result is None


async def test_update_debt_wrong_owner_returns_none(repository):
    debt = _debt(id=1, telegram_user_id=2)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    result = await service.update_debt(1, debt_id=1, monthly_payment=1000)

    assert result is None


# --- Калькулятор досрочного погашения (specs/029, по мотивам YNAB) -----


async def test_simulate_payoff_no_extra_saves_nothing(repository):
    debt = _debt(id=1, remaining_amount=100000, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1, extra_monthly=0)

    assert plan.months_current == 5
    assert plan.months_with_extra == 5
    assert plan.months_saved == 0


async def test_simulate_payoff_extra_payment_shortens_term(repository):
    debt = _debt(id=1, remaining_amount=100000, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1, extra_monthly=30000)

    # 100000 / 20000 = 5 мес текущих, 100000 / 50000 = 2 мес с доплатой
    assert plan.months_current == 5
    assert plan.months_with_extra == 2
    assert plan.months_saved == 3


async def test_simulate_payoff_rounds_up_partial_months(repository):
    """Последний неполный месяц всё равно считается целым — платёж
    в этом месяце ещё не закрыт."""
    debt = _debt(id=1, remaining_amount=100001, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1, extra_monthly=0)

    assert plan.months_current == 6


async def test_simulate_payoff_without_monthly_payment_returns_none(repository):
    debt = _debt(id=1, remaining_amount=100000, monthly_payment=None)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1)

    assert plan is None


async def test_simulate_payoff_already_closed_returns_none(repository):
    debt = _debt(id=1, remaining_amount=0, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1)

    assert plan is None


async def test_simulate_payoff_missing_debt_returns_none(repository):
    repository.get_by_id.return_value = None
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 999)

    assert plan is None


async def test_simulate_payoff_wrong_owner_returns_none(repository):
    debt = _debt(id=1, telegram_user_id=2, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    plan = await service.simulate_payoff(1, 1)

    assert plan is None


async def test_simulate_payoff_negative_extra_raises(repository):
    debt = _debt(id=1, monthly_payment=20000)
    repository.get_by_id.return_value = debt
    service = DebtService(repository)

    with pytest.raises(ValueError):
        await service.simulate_payoff(1, 1, extra_monthly=-100)
