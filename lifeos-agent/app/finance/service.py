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
    Debt,
    Transaction,
)
from app.finance.repository import DebtRepository, FinanceRepository

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


@dataclass
class MonthSummary:
    """Один месяц — для аналитики/тренда (specs/017-finance.md, довесок:
    "добавить аналитику"). year/month, а не date/label — форматирование
    остаётся на вызывающем коде (API/бот сами решают, как показать)."""

    year: int
    month: int
    income_total: int
    expense_total: int

    @property
    def net(self) -> int:
        return self.income_total - self.expense_total


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

    async def monthly_breakdown(
        self, telegram_user_id: int, months: int = 6
    ) -> list[MonthSummary]:
        """Доход/траты по месяцам за последние `months` месяцев, для
        тренда на /ui (specs/017-finance.md, довесок "добавить
        аналитику"). Список ОДНОЙ выборкой (list_since уже фильтрует в
        БД по диапазону), разбивка по месяцам — в Python (ADR-004, тот
        же довод, что у build_period_summary: объём личных финансов
        одного пользователя не требует агрегации в БД).

        Месяцы без единой транзакции всё равно попадают в список нулями
        — иначе график "прыгал" бы по оси, молча пропуская пустые
        месяцы, а не показывая настоящий пробел."""
        now = datetime.now(timezone.utc)
        start_year, start_month = now.year, now.month - (months - 1)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        since = datetime(start_year, start_month, 1, tzinfo=timezone.utc)

        transactions = await self._repository.list_since(telegram_user_id, since)

        order: list[tuple[int, int]] = []
        buckets: dict[tuple[int, int], dict[str, int]] = {}
        year, month = start_year, start_month
        for _ in range(months):
            key = (year, month)
            order.append(key)
            buckets[key] = {"income": 0, "expense": 0}
            month += 1
            if month > 12:
                month = 1
                year += 1

        for t in transactions:
            key = (t.occurred_at.year, t.occurred_at.month)
            bucket = buckets.get(key)
            if bucket is None:
                continue
            bucket["income" if t.kind == INCOME else "expense"] += t.amount

        return [
            MonthSummary(
                year=y,
                month=m,
                income_total=buckets[(y, m)]["income"],
                expense_total=buckets[(y, m)]["expense"],
            )
            for y, m in order
        ]


class DebtService:
    """Долги/задолженности (specs/017-finance.md, довесок). Отдельный
    сервис от FinanceService (ADR-005) — своя модель, свой жизненный
    цикл (остаток уменьшается платежами, не разовая запись)."""

    def __init__(self, repository: DebtRepository) -> None:
        self._repository = repository

    async def add_debt(
        self,
        telegram_user_id: int,
        name: str,
        total_amount: int,
        due_date: Optional[datetime] = None,
    ) -> Debt:
        name = name.strip()
        if not name:
            raise ValueError("Название долга не может быть пустым")
        if total_amount <= 0:
            raise ValueError("Сумма долга должна быть положительной")

        debt = Debt(
            telegram_user_id=telegram_user_id,
            name=name,
            total_amount=total_amount,
            remaining_amount=total_amount,
            due_date=due_date,
        )
        return await self._repository.add(debt)

    async def list_debts(self, telegram_user_id: int) -> list[Debt]:
        return await self._repository.list_by_user(telegram_user_id)

    async def record_payment(
        self, telegram_user_id: int, debt_id: int, amount: int
    ) -> Optional[Debt]:
        if amount <= 0:
            raise ValueError("Сумма платежа должна быть положительной")
        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None:
            return None
        # Не уходит в минус — платёж больше остатка просто закрывает долг
        # (частая ситуация: округление в большую сторону последним
        # платежом), а не превращает Debt в "должны нам".
        debt.remaining_amount = max(0, debt.remaining_amount - amount)
        return await self._repository.save(debt)

    async def delete_debt(self, telegram_user_id: int, debt_id: int) -> Optional[Debt]:
        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None:
            return None
        await self._repository.delete(debt)
        return debt
