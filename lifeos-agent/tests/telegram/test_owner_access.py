"""
Доступ к боту только для владельца (см. app/telegram/bot.py, AUDIT.md C-4)
и устойчивость разбора callback_data (AUDIT.md, B-3).
"""

from datetime import datetime, timezone

from telegram import Chat, Message, Update, User

from app.core.config import Settings
from app.telegram.bot import _owner_filter
from app.telegram.callbacks import _parse_item_id, parse_callback

_OWNER_ID = 414825951
_STRANGER_ID = 999


def _update_from(user_id: int) -> Update:
    """Настоящий telegram.Update — filters.User смотрит на
    update.effective_message, самодельная заглушка сюда не подходит."""
    user = User(id=user_id, first_name="Кто-то", is_bot=False)
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=user_id, type=Chat.PRIVATE),
        from_user=user,
        text="Купить молоко",
    )
    return Update(update_id=1, message=message)


def test_owner_passes_the_filter():
    owner_filter = _owner_filter(Settings(owner_telegram_user_id=_OWNER_ID))

    assert owner_filter.check_update(_update_from(_OWNER_ID))


def test_stranger_is_blocked():
    """Посторонний не должен тратить деньги владельца на OpenRouter и
    грузить свои фото на его Google Drive (см. AUDIT.md, C-4)."""
    owner_filter = _owner_filter(Settings(owner_telegram_user_id=_OWNER_ID))

    assert not owner_filter.check_update(_update_from(_STRANGER_ID))


def test_unconfigured_owner_lets_everyone_in():
    """owner_telegram_user_id=0 — бот ещё не настроен: /start обязан
    отвечать, он как раз и показывает Telegram ID для настройки."""
    owner_filter = _owner_filter(Settings(owner_telegram_user_id=0))

    assert owner_filter.check_update(_update_from(_STRANGER_ID))


def test_parse_callback_reads_normal_data():
    assert parse_callback("t|c|5") == ("t", "c", "5")


def test_parse_callback_survives_garbage():
    """Раньше строка без "|" роняла распаковку (ValueError), исключение
    уходило в лог, а пользователь не получал ответа (AUDIT.md, B-3)."""
    assert parse_callback("мусор") is None
    assert parse_callback("") is None
    assert parse_callback("t|") is None


def test_parse_callback_allows_missing_id():
    """ "w|r|0" действует на весь список; форма без id тоже не должна падать."""
    assert parse_callback("g|noop") == ("g", "noop", "")


def test_parse_item_id_rejects_non_numeric():
    assert _parse_item_id("5") == 5
    assert _parse_item_id("abc") is None
    assert _parse_item_id("") is None
