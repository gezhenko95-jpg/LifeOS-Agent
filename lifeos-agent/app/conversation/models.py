"""
Реплики диалога (specs/027-butler-personas-phase2.md, п.1) — короткая
память ЭТОГО разговора, отдельная от `MemoryEntry` (долгосрочная
память фактов/предпочтений). Реплика «а второй вариант?» без
сохранённого текста предыдущего ответа бота не разрешима — вот для
чего это.

Хранится ПОСТОЯННО (не in-memory/TTL) — решение владельца: API и бот
деплоятся по несколько раз за сессию (см. HANDOFF.md, «Технические
нюансы»), оперативная память отваливалась бы посреди разговора.

Append-only лог, тот же приём, что уже есть у `TaskComment`/
`DebtPayment`/`ContactComment` — не апдейтится, только читается
последними N через `list_recent_turns` (см. history.py).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ROLE_USER = "user"
ROLE_BOT = "bot"


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Уникальный идентификатор записи",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Идентификатор пользователя в Telegram",
    )

    role: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="user|bot — кто произнёс реплику",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Текст реплики",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Момент реплики",
    )
