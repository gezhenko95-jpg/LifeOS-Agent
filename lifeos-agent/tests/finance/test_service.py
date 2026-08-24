"""
FinanceService — repository замокан.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.finance.models import EXPENSE, INCOME, Transaction
from app.finance.service import FinanceService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda t: t  # ведёт себя как реальный add()
    return repo


async def test_add_expense_with_known_category(repository):
    service = FinanceService(repository)

    transaction = await service.add_transaction(
        1, EXPENSE, 500, category="transport", note="такси домой"
    )

    assert transaction.category == "transport"
    assert transaction.amount == 500
    assert transaction.note == "такси домой"
    repository.add.assert_awaited_once()


async def test_add_expense_unknown_category_falls_back_to_other(repository):
    service = FinanceService(repository)

    transaction = await service.add_transaction(1, EXPENSE, 500, category="bogus")

    assert transaction.category == "other"


async def test_add_expense_without_category_falls_back_to_other(repository):
    service = FinanceService(repository)

    transaction = await service.add_transaction(1, EXPENSE, 500)

    assert transaction.category == "other"


async def test_add_income_ignores_category(repository):
    service = FinanceService(repository)

    transaction = await service.add_transaction(1, INCOME, 80000, category="rent")

    assert transaction.category is None
    assert transaction.kind == INCOME


async def test_add_transaction_rejects_non_positive_amount(repository):
    service = FinanceService(repository)

    with pytest.raises(ValueError):
        await service.add_transaction(1, EXPENSE, 0)
    with pytest.raises(ValueError):
        await service.add_transaction(1, EXPENSE, -100)


async def test_add_transaction_rejects_unknown_kind(repository):
    service = FinanceService(repository)

    with pytest.raises(ValueError):
        await service.add_transaction(1, "bogus", 100)


async def test_add_transaction_empty_note_becomes_none(repository):
    service = FinanceService(repository)

    transaction = await service.add_transaction(1, EXPENSE, 100, note="   ")

    assert transaction.note is None


def _transaction(**kwargs) -> Transaction:
    kwargs.setdefault("telegram_user_id", 1)
    kwargs.setdefault("occurred_at", NOW)
    return Transaction(**kwargs)


async def test_build_period_summary_free_money_and_norms(repository):
    """80000 доход, 45000 обязательных (rent+utilities) → 35000 свободных.
    groceries — 30% нормы, transport — 15%."""
    repository.list_since.return_value = [
        _transaction(kind=INCOME, amount=80000),
        _transaction(kind=EXPENSE, category="rent", amount=40000),
        _transaction(kind=EXPENSE, category="utilities", amount=5000),
        _transaction(kind=EXPENSE, category="groceries", amount=6000),
        _transaction(kind=EXPENSE, category="transport", amount=1000),
    ]
    service = FinanceService(repository)

    summary = await service.build_period_summary(1, NOW)

    assert summary.income_total == 80000
    assert summary.mandatory_total == 45000
    assert summary.free_money == 35000
    by_category = {c.category: c for c in summary.categories}
    assert by_category["groceries"].spent == 6000
    assert by_category["groceries"].norm == round(35000 * 0.30)
    assert by_category["groceries"].over_budget is False
    assert by_category["transport"].spent == 1000
    assert by_category["transport"].norm == round(35000 * 0.15)


async def test_build_period_summary_flags_over_budget_category(repository):
    repository.list_since.return_value = [
        _transaction(kind=INCOME, amount=10000),
        _transaction(kind=EXPENSE, category="eating_out", amount=9000),
    ]
    service = FinanceService(repository)

    summary = await service.build_period_summary(1, NOW)

    eating_out = next(c for c in summary.categories if c.category == "eating_out")
    assert eating_out.over_budget is True


async def test_build_period_summary_skips_categories_with_no_spending(repository):
    repository.list_since.return_value = [
        _transaction(kind=INCOME, amount=10000),
        _transaction(kind=EXPENSE, category="groceries", amount=500),
    ]
    service = FinanceService(repository)

    summary = await service.build_period_summary(1, NOW)

    assert [c.category for c in summary.categories] == ["groceries"]


async def test_build_period_summary_empty_period(repository):
    repository.list_since.return_value = []
    service = FinanceService(repository)

    summary = await service.build_period_summary(1, NOW)

    assert summary.income_total == 0
    assert summary.mandatory_total == 0
    assert summary.free_money == 0
    assert summary.categories == []


async def test_delete_transaction_owned(repository):
    transaction = _transaction(id=5)
    repository.get_by_id.return_value = transaction
    service = FinanceService(repository)

    result = await service.delete_transaction(1, 5)

    assert result is transaction
    repository.delete.assert_awaited_once_with(transaction)


async def test_delete_transaction_wrong_owner_returns_none(repository):
    transaction = _transaction(id=5, telegram_user_id=2)
    repository.get_by_id.return_value = transaction
    service = FinanceService(repository)

    result = await service.delete_transaction(1, 5)

    assert result is None
    repository.delete.assert_not_awaited()


async def test_delete_transaction_missing_returns_none(repository):
    repository.get_by_id.return_value = None
    service = FinanceService(repository)

    result = await service.delete_transaction(1, 999)

    assert result is None


async def test_list_recent_transactions_delegates_to_repository(repository):
    repository.list_recent.return_value = [_transaction()]
    service = FinanceService(repository)

    result = await service.list_recent_transactions(1, limit=5)

    assert len(result) == 1
    repository.list_recent.assert_awaited_once_with(1, 5)


# --- Аналитика по месяцам (specs/017, довесок) ------------------------------


async def test_monthly_breakdown_returns_requested_number_of_months(repository):
    repository.list_since.return_value = []
    service = FinanceService(repository)

    months = await service.monthly_breakdown(1, months=6)

    assert len(months) == 6


async def test_monthly_breakdown_last_month_is_current(repository):
    repository.list_since.return_value = []
    service = FinanceService(repository)

    months = await service.monthly_breakdown(1, months=3)

    now = datetime.now(timezone.utc)
    assert (months[-1].year, months[-1].month) == (now.year, now.month)


async def test_monthly_breakdown_groups_by_month(repository):
    this_month = datetime.now(timezone.utc).replace(day=15)
    repository.list_since.return_value = [
        _transaction(kind=INCOME, amount=1000, occurred_at=this_month),
        _transaction(
            kind=EXPENSE, amount=300, category="groceries", occurred_at=this_month
        ),
        _transaction(
            kind=EXPENSE, amount=200, category="transport", occurred_at=this_month
        ),
    ]
    service = FinanceService(repository)

    months = await service.monthly_breakdown(1, months=1)

    assert months[0].income_total == 1000
    assert months[0].expense_total == 500
    assert months[0].net == 500


async def test_monthly_breakdown_ignores_transactions_outside_window(repository):
    old = datetime.now(timezone.utc).replace(year=2000)
    repository.list_since.return_value = [
        _transaction(kind=INCOME, amount=99999, occurred_at=old),
    ]
    service = FinanceService(repository)

    months = await service.monthly_breakdown(1, months=1)

    # list_since сам фильтрует в БД — если бы репозиторий вернул лишнее
    # (замокан, не проверяет диапазон), группировка по бакетам должна
    # молча отбросить то, что не попало ни в один месяц окна.
    assert months[0].income_total == 0
