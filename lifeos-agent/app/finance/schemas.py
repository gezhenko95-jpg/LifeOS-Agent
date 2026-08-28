"""
Pydantic-схемы для Finance Service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TransactionCreate(BaseModel):
    """Данные для создания транзакции."""

    telegram_user_id: int
    kind: str = Field(pattern="^(income|expense)$")
    amount: int = Field(gt=0)
    category: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


class TransactionRead(BaseModel):
    """Представление транзакции в ответах API.

    `category_label` — не поле модели `Transaction` (там только код
    категории), а `Optional[str] = None` по умолчанию: `model_validate`
    в `app/api/finance.py` дозаполняет его человекочитаемой подписью из
    `app/finance/models.py::CATEGORIES`, чтобы `/ui` не заводил свою
    копию этого словаря на JS (см. specs/017-finance.md)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    kind: str
    category: Optional[str] = None
    category_label: Optional[str] = None
    amount: int
    note: Optional[str] = None
    occurred_at: datetime
    created_at: datetime


class CategoryBreakdownRead(BaseModel):
    """Одна строка разбивки по категории в ответе /finance/summary."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    label: str
    spent: int
    norm: int
    over_budget: bool


class FinanceSummaryRead(BaseModel):
    """Итоги периода — то же, что FinanceSummary, но с посчитанным
    over_budget на каждой категории (dataclass-свойство, pydantic
    from_attributes его подхватывает как обычное поле)."""

    model_config = ConfigDict(from_attributes=True)

    income_total: int
    mandatory_total: int
    free_money: int
    categories: list[CategoryBreakdownRead] = Field(default_factory=list)


class MonthSummaryRead(BaseModel):
    """Один месяц в ответе /finance/analytics — net тоже dataclass-
    свойство (income_total − expense_total), как over_budget выше."""

    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    income_total: int
    expense_total: int
    net: int


class BudgetRecommendationRead(BaseModel):
    """Одна строка в ответе /finance/recommendations — чистые числа, без
    AI-фразы поверх (решение владельца, отчёт 24.08 вечер #6)."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    label: str
    avg_monthly: int
    suggested_cap: int


class DebtCreate(BaseModel):
    telegram_user_id: int
    name: str = Field(min_length=1, max_length=100)
    total_amount: int = Field(gt=0)
    due_date: Optional[datetime] = None


class DebtPayment(BaseModel):
    telegram_user_id: int
    amount: int = Field(gt=0)


class DebtUpdate(BaseModel):
    """План рассрочки (specs/017, довесок волна 7) — due_date/monthly_payment/
    next_payment_due все независимы и все необязательные, каждое со своим
    clear-флагом (тот же приём, что clear_contact у задач: None значит "не
    трогать", а не "сбросить")."""

    due_date: Optional[datetime] = None
    clear_due_date: bool = False
    monthly_payment: Optional[int] = Field(default=None, gt=0)
    clear_monthly_payment: bool = False
    next_payment_due: Optional[datetime] = None
    clear_next_payment_due: bool = False


class DebtPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    debt_id: int
    amount: int
    paid_at: datetime


class PayoffPlanRead(BaseModel):
    """Ответ калькулятора досрочного погашения (specs/029) — months_saved
    dataclass-свойство (months_current − months_with_extra), как
    over_budget/net у соседних схем выше."""

    model_config = ConfigDict(from_attributes=True)

    months_current: int
    months_with_extra: int
    months_saved: int


class DebtRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    name: str
    total_amount: int
    remaining_amount: int
    due_date: Optional[datetime] = None
    monthly_payment: Optional[int] = None
    next_payment_due: Optional[datetime] = None
    created_at: datetime


class DebtPriorityRead(BaseModel):
    """Один долг в автоматическом порядке приоритета (specs/030) —
    собирается вручную в app/api/finance.py (DebtRead.model_validate на
    вложенном ORM-объекте), не через model_validate(from_attributes) на
    самом DebtPriority: проще и явнее, тот же приём, что _to_read в
    app/api/shop.py."""

    debt: DebtRead
    rank: int
    reason: str
