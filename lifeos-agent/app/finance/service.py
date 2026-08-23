"""
Finance Service.

Вся бизнес-логика учёта финансов здесь. Repository — только БД,
Conversation/scheduler — только вызывают этот сервис. Расчёт свободных
денег и норм — детерминированный код (ADR-004), никакого AI: LLM (см.
app/scheduler/finance_report.py) только формулирует фразу поверх уже
готовых чисел.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.finance.models import (
    CATEGORIES,
    CATEGORY_NORM_PERCENT,
    EXPENSE,
    INCOME,
    MANDATORY_CATEGORIES,
    Transaction,
)
from app.finance.repository import FinanceRepository

_KINDS = {INCOME, EXPENSE}


@dataclass
class CategoryBreakdown:
    category: str
    label: str
    spent: int
    norm: int

    @property
    def over_budget(self) -> bool:
        return self.spent > self.norm


@dataclass
class FinanceSummary:
    income_total: int
    mandatory_total: int
    free_money: int
    # Только категории, по которым была хоть одна трата за период —
    # тот же принцип, что у пустых секций брифинга/дайджеста (незачем
    # показывать "0 из 0" по каждой из семи категорий).
    categories: list[CategoryBreakdown] = field(default_factory=list)


class FinanceService:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    async def add_transaction(
        self,
        telegram_user_id: int,
        kind: str,
        amount: int,
        category: Optional[str] = None,
        note: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> Transaction:
        if kind not in _KINDS:
            raise ValueError(f"Неизвестный тип транзакции: {kind}")
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        if kind == EXPENSE:
            # Категория не распознана из текста или не из списка — "other",
            # а не отказ сохранить трату (пользователь и так уже написал
            # сумму, молча потерять её из-за неизвестного слова хуже, чем
            # положить в "другое", см. specs/017-finance.md).
            if category not in CATEGORIES:
                category = "other"
        else:
            # Доход не делится на категории — категория для kind=income
            # всегда None, даже если случайно передана.
            category = None

        transaction = Transaction(
            telegram_user_id=telegram_user_id,
            kind=kind,
            category=category,
            amount=amount,
            note=(note or "").strip() or None,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
        return await self._repository.add(transaction)

    async def list_transactions_since(
        self, telegram_user_id: int, since: datetime
    ) -> list[Transaction]:
        return await self._repository.list_since(telegram_user_id, since)

    async def list_recent_transactions(
        self, telegram_user_id: int, limit: int = 10
    ) -> list[Transaction]:
        return await self._repository.list_recent(telegram_user_id, limit)

    async def delete_transaction(
        self, telegram_user_id: int, transaction_id: int
    ) -> Optional[Transaction]:
        transaction = owned_or_none(
            await self._repository.get_by_id(transaction_id), telegram_user_id
        )
        if transaction is None:
            return None
        await self._repository.delete(transaction)
        return transaction

    async def build_period_summary(
        self, telegram_user_id: int, since: datetime
    ) -> FinanceSummary:
        """Свободные деньги = доход − обязательные категории (rent/
        utilities/subscriptions/credit) за период. Норма каждой
        необязательной категории = её процент (CATEGORY_NORM_PERCENT) от
        свободных денег. Обе части формулы уже приняты владельцем, здесь
        только арифметика поверх готовых транзакций."""
        transactions = await self._repository.list_since(telegram_user_id, since)

        income_total = sum(t.amount for t in transactions if t.kind == INCOME)
        mandatory_total = sum(
            t.amount
            for t in transactions
            if t.kind == EXPENSE and t.category in MANDATORY_CATEGORIES
        )
        free_money = income_total - mandatory_total

        spent_by_category: dict[str, int] = {}
        for t in transactions:
            if t.kind != EXPENSE or t.category not in CATEGORY_NORM_PERCENT:
                continue
            spent_by_category[t.category] = (
                spent_by_category.get(t.category, 0) + t.amount
            )

        categories = [
            CategoryBreakdown(
                category=category,
                label=CATEGORIES[category],
                spent=spent,
                norm=round(free_money * CATEGORY_NORM_PERCENT[category] / 100),
            )
            for category, spent in spent_by_category.items()
        ]
        # Стабильный порядок — по проценту нормы (крупные категории
        # первыми), не по случайному порядку словаря/вставки.
        categories.sort(key=lambda c: CATEGORY_NORM_PERCENT[c.category], reverse=True)

        return FinanceSummary(
            income_total=income_total,
            mandatory_total=mandatory_total,
            free_money=free_money,
            categories=categories,
        )
