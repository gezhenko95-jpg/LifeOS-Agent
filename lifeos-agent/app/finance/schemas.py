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
