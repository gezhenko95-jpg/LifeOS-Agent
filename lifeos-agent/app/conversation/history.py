"""
Память диалога (specs/027-butler-personas-phase2.md, п.1) — репозиторий
и тонкий сервис поверх `ConversationTurn`.

Единственный потребитель — `ConversationEngine._chat_reply`
(разговорный AI-фолбэк, chat_reply.py): записывает обе стороны обмена
(пользователь + персонаж) и подмешивает последние реплики в системный
промпт следующего разговорного ответа.
"""

from sqlalchemy import desc, select

from app.conversation.models import ROLE_BOT, ROLE_USER, ConversationTurn
from app.core.repository import BaseRepository

# Последние 8 реплик (4 обмена владелец/бот) — тот же порядок величины,
# что у остальных LIMIT-мест разговорного контекста проекта
# (_MAX_CHAT_CONTEXT_ITEMS у Memory, _MAX_RECALL_RESULTS): не "весь
# диалог", иначе стоимость AI-вызова росла бы без границ вместе с
# историей общения.
DEFAULT_HISTORY_LIMIT = 8


class ConversationHistoryRepository(BaseRepository[ConversationTurn]):
    model = ConversationTurn

    async def list_recent(
        self, telegram_user_id: int, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> list[ConversationTurn]:
        """Хронологический порядок (старые сверху) — так их удобно сразу
        вставлять в промпт. Запрос идёт DESC+LIMIT (иначе LIMIT взял бы
        самые старые записи из всей истории, а не последние), результат
        разворачивается в Python.

        Сортировка по (created_at, id), не только created_at: два
        подряд record_turn (пользователь+бот в одном record_exchange)
        нередко попадают в одну и ту же секунду — `server_default
        func.now()` не различает их по времени, и без id как
        тай-брейкера порядок реплик внутри секунды не гарантирован
        (SQLite отдавал их в обратном порядке на живом тесте)."""
        query = (
            select(ConversationTurn)
            .where(ConversationTurn.telegram_user_id == telegram_user_id)
            .order_by(desc(ConversationTurn.created_at), desc(ConversationTurn.id))
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(reversed(result.scalars().all()))


class ConversationHistoryService:
    def __init__(self, repository: ConversationHistoryRepository) -> None:
        self._repository = repository

    async def record_turn(self, telegram_user_id: int, role: str, content: str) -> None:
        turn = ConversationTurn(
            telegram_user_id=telegram_user_id, role=role, content=content
        )
        await self._repository.add(turn)

    async def record_exchange(
        self, telegram_user_id: int, user_text: str, bot_reply: str
    ) -> None:
        """Обе стороны одного обмена — вызывающему коду (engine.py) не
        нужно помнить порядок ролей дважды."""
        await self.record_turn(telegram_user_id, ROLE_USER, user_text)
        await self.record_turn(telegram_user_id, ROLE_BOT, bot_reply)

    async def format_recent(
        self, telegram_user_id: int, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> str:
        """Готовая к вставке в промпт строка, пустая если истории ещё
        нет — вызывающему коду (chat_reply.py) не нужно самому решать,
        как подписывать роли."""
        turns = await self._repository.list_recent(telegram_user_id, limit=limit)
        if not turns:
            return ""
        speaker = {ROLE_USER: "Пользователь", ROLE_BOT: "Ты"}
        return "\n".join(
            f"{speaker.get(turn.role, turn.role)}: {turn.content}" for turn in turns
        )
