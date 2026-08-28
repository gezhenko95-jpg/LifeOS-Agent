"""
Модели фермы (specs/028, фаза 2).

Три таблицы, все append-only или почти: та же философия, что уже
проведена через `app/rewards/`/`app/shop/` — состояние (сколько семян
осталось, сколько сена в амбаре) ВЫВОДИТСЯ из истории, а не хранится
отдельным изменяемым счётчиком, который может с историей разойтись.

`FarmPlot` — исключение: у неё есть поле, которое меняется
(`harvested_at`), потому что "грядка убрана" — это состояние конкретной
грядки, а не производная величина. Расход семян/ускорителей на посадку
и сбор сена в амбар выводятся уже ИЗ строк `FarmPlot`, отдельных
счётчиков под них нет.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FarmPlot(Base):
    """Одна грядка от посадки до (не обязательно случившегося) сбора.

    Сколько семян потрачено пользователем за всё время — COUNT(*) строк
    этой таблицы для него; отдельного счётчика "остаток семян" нет по
    той же причине, что у `total_coins`: две независимые цифры имеют
    свойство расходиться, одна производная — никогда.
    """

    __tablename__ = "farm_plots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    planted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ready_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Момент, когда грядку можно убирать — опрашивается сервисом "
        "при каждом статусе, отдельной джобы-уведомления в фазе 2 нет",
    )

    fertilized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="Удобрение применено при посадке — вдвое короче ready_at, "
        "поле нужно только для отображения значка на фронте",
    )

    hay_yield: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Сколько сена даст сбор этой грядки"
    )

    harvested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL — ещё растёт или созрела, но не собрана",
    )

    ready_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда отправлено уведомление 'сено готово' "
        "(app/telegram/jobs.py::send_farm_pet_notifications_job), "
        "NULL — ещё не отправлялось",
    )


class FarmSupplyUse(Base):
    """Расход купленного в магазине на нужды фермы: посадка тратит семя
    (и, если выбрано, ускоритель "Удобрение"), полив тратит "Тёплый
    дождь". Один и тот же ledger-приём, что у `CoinTransaction`
    (`app/shop/models.py`) — остаток = куплено (`ShopRepository.
    purchased_counts`) минус потрачено (эта таблица), а не два
    независимых числа."""

    __tablename__ = "farm_supply_use"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    item_id: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        index=True,
        comment="Товар из app/shop/catalog.py — seed_clover/booster_*",
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HayConsumption(Base):
    """Сено, скормленное питомцу (фаза 3, `app/pet/`). Живёт в домене
    фермы, а не питомца, — сено ферма производит и ферма же ведёт его
    учёт; питомец только просит вычесть из амбара."""

    __tablename__ = "hay_consumption"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
