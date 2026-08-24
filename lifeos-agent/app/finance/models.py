"""
Модель финансовой транзакции (specs/017-finance.md) + фиксированный
список категорий. Категории живут в коде, не в БД — так решено владельцем
(см. HANDOFF): не заводить пользовательскую таблицу категорий ради
гибкости, которая не нужна.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

INCOME = "income"
EXPENSE = "expense"

# Название категории → подпись с эмодзи для сообщений/отчёта.
CATEGORIES: dict[str, str] = {
    "rent": "🏠 Аренда/ипотека",
    "utilities": "💡 Коммуналка",
    "subscriptions": "🔁 Подписки",
    "credit": "🏦 Кредит/рассрочка",
    "groceries": "🛒 Продукты",
    "transport": "🚕 Транспорт",
    "eating_out": "🍔 Кафе",
    "health": "💊 Здоровье",
    "entertainment": "🎉 Развлечения",
    "shopping": "🛍 Покупки",
    "other": "❓ Другое",
}

# Обязательные платежи вычитаются из дохода целиком и не участвуют в
# процентной норме — это НЕ отдельное поле kind, а свойство самой
# категории, чтобы не заводить второе измерение поверх и так
# фиксированного списка (specs/017-finance.md).
MANDATORY_CATEGORIES: frozenset[str] = frozenset(
    {"rent", "utilities", "subscriptions", "credit"}
)

# Норма — процент от СВОБОДНЫХ денег (после вычета обязательных),
# только для категорий вне MANDATORY_CATEGORIES. Сумма = 100.
CATEGORY_NORM_PERCENT: dict[str, int] = {
    "groceries": 30,
    "transport": 15,
    "eating_out": 15,
    "health": 10,
    "entertainment": 15,
    "shopping": 10,
    "other": 5,
}

DISCRETIONARY_CATEGORIES: frozenset[str] = frozenset(CATEGORY_NORM_PERCENT)


class Transaction(Base):
    """Одна запись дохода или траты. `category` осмысленна только для
    kind=expense — для income всегда None (доход не делится на
    категории, только траты)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор транзакции",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, comment='"income" или "expense"'
    )

    category: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Одна из CATEGORIES; всегда None для income",
    )

    amount: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Сумма в рублях, целое, > 0"
    )

    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Остаток свободного текста после суммы/категории",
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Когда произошло (по умолчанию — момент сообщения)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда фактически записано",
    )


class Debt(Base):
    """Долг/задолженность со сроком — отдельная сущность от Transaction
    (specs/017-finance.md, довесок). Ежемесячный платёж по кредиту
    по-прежнему логируется обычной тратой в категории "credit" — Debt
    только отслеживает остаток и срок, в расчёт свободных денег не
    входит (см. FinanceService.build_period_summary)."""

    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    total_amount: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Исходная сумма долга в рублях"
    )

    remaining_amount: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Текущий остаток — уменьшается платежами"
    )

    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Срок закрытия"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
