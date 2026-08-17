"""
«Следующее сообщение — это ответ на кнопку».

Кнопки второго уровня (см. app/telegram/keyboards.py) часто просят
дописать одно значение: название для полки, имя нового дайджеста, имя
канала, тему для поиска по дневнику. Между нажатием кнопки и следующим
сообщением нужно где-то помнить, чего мы ждём.

Почему context.user_data, а не таблица pending_prompts. Таблица — про
ДИАЛОГ бота с пользователем (проактивный вопрос, дневниковое
приглашение): вопрос живёт часами, переживает рестарт, участвует в
AI-разборе ответа (см. app/conversation/engine.py). Здесь другое:
техническое «жду одно слово прямо сейчас», актуальное секунды. Хранить
это в БД — лишняя миграция и лишний поход в базу на КАЖДОЕ сообщение
(ADR-004: простой код лучше). Плата за простоту одна: рестарт бота
забывает ожидание, и следующее сообщение разберётся как обычный текст —
пользователь просто нажмёт кнопку ещё раз.

Ожидание одноразовое: `pop` его снимает. Нажатие любой кнопки постоянного
меню тоже снимает (см. handlers.py) — иначе «➕ Добавить» и уход в другой
раздел оставили бы висеть ловушку, которая проглотит следующее сообщение.
"""

from dataclasses import dataclass
from typing import Any, Optional

# Чего ждём от следующего сообщения.
WATCHLIST_ADD = "watchlist_add"
JOURNAL_SEARCH = "journal_search"
DIGEST_NEW = "digest_new"
DIGEST_CHANNEL = "digest_channel"

_KEY = "pending_input"


@dataclass(frozen=True)
class PendingInput:
    kind: str
    # id дайджеста для DIGEST_CHANNEL; остальным видам контекст не нужен.
    digest_id: Optional[int] = None


def set_pending(user_data: Optional[dict[str, Any]], pending: PendingInput) -> None:
    """user_data может быть None (у голосовых/служебных апдейтов PTB её не
    создаёт) — тогда просто не запоминаем: пользователь получит обычный
    разбор текста, а не тихую ошибку."""
    if user_data is None:
        return
    user_data[_KEY] = pending


def pop_pending(user_data: Optional[dict[str, Any]]) -> Optional[PendingInput]:
    if not user_data:
        return None
    pending = user_data.pop(_KEY, None)
    return pending if isinstance(pending, PendingInput) else None


def clear_pending(user_data: Optional[dict[str, Any]]) -> None:
    if user_data:
        user_data.pop(_KEY, None)
