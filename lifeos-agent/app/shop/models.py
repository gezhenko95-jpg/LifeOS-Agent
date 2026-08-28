"""
Модель расхода монет (CoinTransaction) — единственное место, где
накопленный баланс может уменьшиться.

Почему отдельная таблица, а не поле `balance` у пользователя
(вариант (A) из specs/028-farm-tamagotchi-rewards.md): существующий
RewardsService.total_coins — не хранимое число, а сумма, пересчитанная
из всей истории чек-инов при каждом запросе (см. докстринг
app/rewards/coins.py::total_coins). Перевод его в хранимый счётчик
переписал бы уже работающую и покрытую тестами механику ради фичи,
которой достаточно вычитания сверху. Здесь только траты; заработок
по-прежнему считает rewards, ничего в нём менять не пришлось.

Таблица append-only, как и checkins: покупка — исторический факт,
её не редактируют и не удаляют. Отсюда же берётся инвентарь (что
куплено) — отдельной таблицы под него нет, он выводится из истории.

`amount` со знаком, а не отдельная колонка "потрачено": поле заранее
терпит будущие НАЧИСЛЕНИЯ мимо чек-ина (награда за цель, компенсация
за баг) — их не пришлось бы вписывать в историю визитов, которая про
другое.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Значения `reason`. Строкой, а не Enum в БД: добавление нового повода
# не должно требовать миграции типа (тот же довод, что у status в
# focus_sessions).
PURCHASE = "purchase"
# Награда за завершённую фокус-сессию (specs/029) — то самое "будущее
# начисление мимо чек-ина", под которое поле amount уже было спроектировано
# знаковым (см. докстринг ниже). purchased_counts фильтрует по
# reason == PURCHASE, так что этот повод не попадает в инвентарь магазина.
FOCUS_REWARD = "focus_reward"
# Три новых повода specs/030 — тот же принцип: начисление мимо чек-ина,
# не попадает в purchased_counts (фильтр по reason == PURCHASE).
PET_ADVENTURE = "pet_adventure"
GOAL_BOSS_DEFEATED = "goal_boss_defeated"
TASK_REWARD = "task_reward"


class CoinTransaction(Base):
    """Одно движение монет: покупка в магазине (amount < 0) или, в
    будущем, начисление мимо ежедневного чек-ина (amount > 0)."""

    __tablename__ = "coin_transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор движения",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Монеты со знаком: трата отрицательная, начисление положительное",
    )

    reason: Mapped[str] = mapped_column(
        String(length=32), nullable=False, comment="Повод движения, напр. purchase"
    )

    item_id: Mapped[str | None] = mapped_column(
        String(length=64),
        nullable=True,
        index=True,
        comment="Товар из каталога (app/shop/catalog.py), если движение — покупка",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Когда произошло движение",
    )
