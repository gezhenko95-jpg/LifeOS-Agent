"""
Finance Service.

Вся бизнес-логика учёта финансов здесь. Repository — только БД,
Conversation/scheduler — только вызывают этот сервис. Расчёт свободных
денег и норм — детерминированный код (ADR-004), никакого AI: LLM (см.
app/scheduler/finance_report.py) только формулирует фразу поверх уже
готовых чисел.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.finance.models import (
    CATEGORIES,
    CATEGORY_NORM_PERCENT,
    DISCRETIONARY_CATEGORIES,
    EXPENSE,
    INCOME,
    MANDATORY_CATEGORIES,
    Debt,
    DebtPayment,
    Transaction,
)
from app.finance.repository import (
    DebtPaymentRepository,
    DebtRepository,
    FinanceRepository,
)

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
class BudgetRecommendation:
    """Одна категория в /finance/recommendations (отчёт владельца 24.08,
    вечер #6, волна 8: "сколько тратить на еду в этом месяце и прочее").
    suggested_cap = avg_monthly — чистый расчёт по истории, без AI-фразы
    поверх (решение владельца, ADR-004: простой код лучше LLM)."""

    category: str
    label: str
    avg_monthly: int
    suggested_cap: int


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

    async def build_budget_recommendations(
        self, telegram_user_id: int, months: int = 3
    ) -> list[BudgetRecommendation]:
        """Среднее по необязательной категории (DISCRETIONARY_CATEGORIES —
        обязательные rent/utilities/subscriptions/credit не участвуют, у
        них нет смысла "сколько потратить", сумма фиксирована) за
        последние `months` ЗАКРЫТЫХ месяцев, без текущего — он ещё не
        закончился, средним по нему только занизили бы рекомендацию.
        Пустой список — если истории меньше `months` месяцев ещё нет
        смысла что-то советовать, а не показывать случайное число по
        одной трате."""
        now = datetime.now(timezone.utc)
        end_year, end_month = now.year, now.month
        start_year, start_month = end_year, end_month - months
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        since = datetime(start_year, start_month, 1, tzinfo=timezone.utc)
        current_month_start = datetime(end_year, end_month, 1, tzinfo=timezone.utc)

        transactions = await self._repository.list_since(telegram_user_id, since)

        spent_by_category: dict[str, int] = {}
        for t in transactions:
            if t.kind != EXPENSE or t.category not in DISCRETIONARY_CATEGORIES:
                continue
            # SQLite (тесты) отдаёт offset-naive datetime даже из
            # DateTime(timezone=True)-колонки — тот же фикс, что уже
            # применён в nudges.py/keyboards.py для last_contact_at.
            occurred_at = t.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            if occurred_at >= current_month_start:
                continue  # текущий месяц не закончился — не в счёт
            spent_by_category[t.category] = (
                spent_by_category.get(t.category, 0) + t.amount
            )

        recommendations = [
            BudgetRecommendation(
                category=category,
                label=CATEGORIES[category],
                avg_monthly=round(spent / months),
                suggested_cap=round(spent / months),
            )
            for category, spent in spent_by_category.items()
        ]
        recommendations.sort(key=lambda r: r.avg_monthly, reverse=True)
        return recommendations


@dataclass
class PayoffPlan:
    """Результат калькулятора досрочного погашения (specs/029, по
    мотивам YNAB) — сколько месяцев осталось сейчас и сколько останется,
    если добавить extra_monthly сверху уже заданного плана рассрочки.
    Без процентной ставки: Debt её не хранит (владелец не вводит её по
    каждому долгу), считаем только сдвиг срока, не "экономию на
    процентах"."""

    months_current: int
    months_with_extra: int

    @property
    def months_saved(self) -> int:
        return self.months_current - self.months_with_extra


@dataclass
class DebtPriority:
    """Один долг в автоматическом порядке приоритета (specs/030) — с
    человекочитаемым обоснованием, а не просто числом: владелец должен
    понимать ПОЧЕМУ система советует именно этот долг, не только что."""

    debt: Debt
    rank: int
    reason: str


# Долг со сроком в пределах этого окна — срочность важнее психологии
# снежного кома (specs/030): просрочка стоит реальных денег/истории,
# маленький остаток без близкого срока подождёт.
_DUE_SOON_DAYS = 30


class DebtService:
    """Долги/задолженности (specs/017-finance.md, довесок). Отдельный
    сервис от FinanceService (ADR-005) — своя модель, свой жизненный
    цикл (остаток уменьшается платежами, не разовая запись)."""

    def __init__(
        self,
        repository: DebtRepository,
        payment_repository: Optional[DebtPaymentRepository] = None,
    ) -> None:
        self._repository = repository
        # Опционально (тот же приём, что contact_repository у TaskService) —
        # без него record_payment по-прежнему двигает remaining_amount, но
        # не пишет лог, list_payments возвращает пусто. Существующие тесты
        # DebtService(repository) без второго аргумента не ломаются.
        self._payments = payment_repository

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
        saved = await self._repository.save(debt)
        if self._payments is not None:
            await self._payments.add(DebtPayment(debt_id=debt_id, amount=amount))
        return saved

    async def list_payments(
        self, telegram_user_id: int, debt_id: int
    ) -> list[DebtPayment]:
        """История платежей для графика на /ui — пусто, если долг чужой
        или сервис собран без payment_repository (см. __init__)."""
        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None or self._payments is None:
            return []
        return await self._payments.list_by_debt(debt_id)

    async def update_debt(
        self,
        telegram_user_id: int,
        debt_id: int,
        due_date: Optional[datetime] = None,
        clear_due_date: bool = False,
        monthly_payment: Optional[int] = None,
        clear_monthly_payment: bool = False,
        next_payment_due: Optional[datetime] = None,
        clear_next_payment_due: bool = False,
    ) -> Optional[Debt]:
        """План рассрочки — оба поля необязательные и независимые от
        due_date (срок закрытия ВСЕГО долга) и от remaining_amount
        (двигается только платежами). Дата следующего платежа не
        пересчитывается сама — владелец двигает её вручную здесь же
        (см. комментарий у Debt.next_payment_due, осознанно не строим
        авто-scheduler для v1)."""
        if monthly_payment is not None and monthly_payment <= 0:
            raise ValueError("Ежемесячный платёж должен быть положительным")

        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None:
            return None

        if clear_due_date:
            debt.due_date = None
        elif due_date is not None:
            debt.due_date = due_date
        if clear_monthly_payment:
            debt.monthly_payment = None
        elif monthly_payment is not None:
            debt.monthly_payment = monthly_payment
        if clear_next_payment_due:
            debt.next_payment_due = None
        elif next_payment_due is not None:
            debt.next_payment_due = next_payment_due

        return await self._repository.save(debt)

    async def simulate_payoff(
        self, telegram_user_id: int, debt_id: int, extra_monthly: int = 0
    ) -> Optional[PayoffPlan]:
        """Калькулятор "добавь X₽/мес — закроешь на N месяцев раньше"
        (specs/029, по мотивам YNAB). None — долг чужой/не найден, нет
        плана рассрочки (monthly_payment не задан — нечего считать) или
        уже закрыт (remaining_amount <= 0 — сравнивать месяцы не с чем)."""
        if extra_monthly < 0:
            raise ValueError("Доплата не может быть отрицательной")

        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None or debt.monthly_payment is None or debt.remaining_amount <= 0:
            return None

        months_current = math.ceil(debt.remaining_amount / debt.monthly_payment)
        new_payment = debt.monthly_payment + extra_monthly
        months_with_extra = math.ceil(debt.remaining_amount / new_payment)
        return PayoffPlan(
            months_current=months_current, months_with_extra=months_with_extra
        )

    async def rank_by_priority(self, telegram_user_id: int) -> list[DebtPriority]:
        """С какого долга начать (specs/030) — автоматически, без выбора
        стратегии владельцем. `Debt` не хранит процентную ставку (см.
        PayoffPlan), поэтому настоящая "лавина" (по проценту) невозможна
        — вместо неё два уровня: срок платежа, если он скоро, иначе
        снежный ком (наименьший остаток первым). Закрытые долги
        (remaining_amount <= 0) не участвуют — приоритезировать нечего."""
        debts = [
            d
            for d in await self._repository.list_by_user(telegram_user_id)
            if d.remaining_amount > 0
        ]
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=_DUE_SOON_DAYS)

        def _due_soon(debt: Debt) -> bool:
            if debt.due_date is None:
                return False
            due = (
                debt.due_date
                if debt.due_date.tzinfo
                else debt.due_date.replace(tzinfo=timezone.utc)
            )
            return due <= soon

        urgent = sorted(
            (d for d in debts if _due_soon(d)),
            key=lambda d: d.due_date,
        )
        rest = sorted(
            (d for d in debts if not _due_soon(d)),
            key=lambda d: d.remaining_amount,
        )

        ranked: list[DebtPriority] = []
        for rank, debt in enumerate(urgent, start=1):
            ranked.append(
                DebtPriority(debt=debt, rank=rank, reason="срок платежа скоро")
            )
        for debt in rest:
            ranked.append(
                DebtPriority(
                    debt=debt,
                    rank=len(ranked) + 1,
                    reason="меньше всего осталось — быстрая победа",
                )
            )
        return ranked

    async def delete_debt(self, telegram_user_id: int, debt_id: int) -> Optional[Debt]:
        debt = owned_or_none(
            await self._repository.get_by_id(debt_id), telegram_user_id
        )
        if debt is None:
            return None
        await self._repository.delete(debt)
        return debt
