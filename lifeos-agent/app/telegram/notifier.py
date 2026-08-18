"""
Отправка сообщения владельцу из процесса, где нет работающего бота.

Нужно API: он живёт в отдельном контейнере (см. docker-compose.yml), и
`context.bot` из джоб там недоступен. Токен у API есть — оба контейнера
читают один `.env`.

Модуль намеренно узкий: одна функция «отправить текст владельцу». Всё,
что сложнее (клавиатуры, фото, редактирование), делает бот — тащить это
в API значит заводить второй бот-процесс на ровном месте.
"""

import logging
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_bot_cache: dict[str, Bot] = {}


class NotifyError(Exception):
    """Сообщение не доставлено. Вызывающий код решает, что показать."""


def get_notifier_bot(settings: Optional[Settings] = None) -> Optional[Bot]:
    """Bot для отправки, либо None, если токен не задан.

    Кэшируется по токену — один экземпляр на процесс, как get_ai_client:
    новый Bot на каждый запрос поднимал бы новое TLS-соединение к
    api.telegram.org (та же правка, что делали для OpenRouter,
    см. AUDIT.md, P-4).
    """
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        return None

    cached = _bot_cache.get(settings.telegram_bot_token)
    if cached is None:
        cached = Bot(token=settings.telegram_bot_token)
        _bot_cache[settings.telegram_bot_token] = cached
    return cached


async def send_to_owner(text: str, settings: Optional[Settings] = None) -> None:
    """Отправить текст владельцу. NotifyError — если не получилось.

    Пустой токен или незаданный владелец — это НЕ «отправили», а отказ:
    забытая настройка не должна выглядеть успехом (тот же принцип, что у
    пустого api_token, который закрывает API, а не открывает его).
    """
    settings = settings or get_settings()
    bot = get_notifier_bot(settings)
    if bot is None:
        raise NotifyError("Токен бота не настроен")
    if not settings.owner_telegram_user_id:
        raise NotifyError("Владелец не задан")

    try:
        await bot.send_message(chat_id=settings.owner_telegram_user_id, text=text)
    except TelegramError as exc:
        logger.warning("Сообщение владельцу не доставлено: %s", exc)
        raise NotifyError(str(exc)) from exc
