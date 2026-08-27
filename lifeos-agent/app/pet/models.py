"""
Модель питомца.

Один питомец на аккаунт (ответ владельца 27.08, specs/028) — без
инвентаря питомцев и переключателя "активный питомец", поэтому
`telegram_user_id` уникален, а не просто индексирован.

Голод и настроение НЕ хранятся полями — они выводятся из `last_fed_at`
чистой функцией в service.py (та же философия, что у `total_coins`:
производное состояние не может разойтись с историей, потому что не
существует отдельно от неё). Хранится только то, что не выводимо:
момент последнего кормления и счётчик смертей — честная память о
пренебрежении, которую кормление НЕ стирает (см. докстринг
`deaths_count`).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    last_fed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Голод/настроение/болезнь/смерть — чистая функция от "
        "этого поля, см. app/pet/service.py",
    )

    deaths_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Сколько раз питомец умирал от пренебрежения — реальная "
        "цена бездействия (решение владельца, specs/028); кормление "
        "после смерти запрещено, снять её может только явное "
        "adopt_new_pet, которое инкрементит это поле",
    )
