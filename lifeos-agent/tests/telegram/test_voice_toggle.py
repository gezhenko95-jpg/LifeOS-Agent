"""
Выключатель голосового ввода (Settings.voice_input_enabled).

Фича выключена не потому, что сломана: транскрипция — единственная
AI-статья, которая стоит заметных денег, а модель монетизации ещё не
выбрана (см. MULTIUSER.md). Код сохранён целиком, поэтому здесь
проверяется ровно одно: выключено — хендлер голосовых не зарегистрирован
(бот молчит на голосовое), включено — зарегистрирован обратно.

Собирать настоящий Application ради этого не нужно и нельзя (требует
живого токена), поэтому проверяем сам факт регистрации через фейковое
приложение.
"""

from unittest.mock import MagicMock, patch

from telegram.ext import MessageHandler, filters

from app.core.config import Settings
from app.telegram import bot as bot_module

_SETTINGS = {
    "telegram_bot_token": "123:TEST",
    "owner_telegram_user_id": 414825951,
    # Джобы к этому тесту отношения не имеют, а без выключения они
    # полезли бы в job_queue фейкового приложения.
    "morning_briefing_enabled": False,
    "evening_reflection_enabled": False,
    "task_reminders_enabled": False,
    "proactive_prompts_enabled": False,
    "weekly_digest_enabled": False,
    "digest_enabled": False,
    "nudges_enabled": False,
    "monthly_insights_enabled": False,
    "memory_embeddings_enabled": False,
}


def _registered_handlers(**overrides) -> list:
    settings = Settings(**{**_SETTINGS, **overrides})
    application = MagicMock()
    handlers: list = []
    application.add_handler.side_effect = handlers.append

    with (
        patch.object(bot_module, "get_settings", return_value=settings),
        patch.object(bot_module.Application, "builder") as builder,
    ):
        builder.return_value.token.return_value.build.return_value = application
        bot_module.build_application()

    return handlers


def _handles_voice(handler) -> bool:
    return isinstance(handler, MessageHandler) and "VOICE" in str(handler.filters)


def test_voice_handler_is_not_registered_by_default():
    """По умолчанию голосовые не обрабатываются вообще — на голосовое
    сообщение бот не отвечает и нигде о фиче не упоминает."""
    assert not any(_handles_voice(h) for h in _registered_handlers())


def test_voice_handler_comes_back_with_one_setting():
    assert any(
        _handles_voice(h) for h in _registered_handlers(voice_input_enabled=True)
    )


def test_text_handler_is_registered_either_way():
    """Выключение голоса не должно задеть обычные сообщения."""
    for enabled in (False, True):
        handlers = _registered_handlers(voice_input_enabled=enabled)
        assert any(
            isinstance(h, MessageHandler) and h.filters is not filters.VOICE
            for h in handlers
        )
