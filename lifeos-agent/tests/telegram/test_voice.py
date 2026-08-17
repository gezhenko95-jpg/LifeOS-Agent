"""
Голосовой ввод (см. specs/012-voice-input.md, AUDIT.md-стиль тестов —
проверяем то, что реально можно дёшево проверить без реального
Telegram-бота/БД: ветвление handle_voice_message и роутинг
_route_parsed_text; полный Telegram-plumbing get_file/download_as_bytearray
в проекте нигде не тестируется даже для фото, не нарушаем этот баланс).

ВАЖНО: сама фича сейчас ВЫКЛЮЧЕНА (`Settings.voice_input_enabled=False`) —
хендлер не регистрируется, бот на голосовые молчит. Тесты ниже проверяют
сам хендлер и остаются в силе: код рабочий и возвращается одной
настройкой. Регистрацию проверяет test_voice_toggle.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.client import AIServiceError
from app.core.config import Settings
from app.telegram import handlers


def _update_with_voice(duration: int = 10) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.voice = SimpleNamespace(file_id="voice-file-id", duration=duration)
    update.effective_user = SimpleNamespace(id=414825951)
    return update


def _context() -> MagicMock:
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"ogg-bytes"))
        )
    )
    return context


async def test_voice_replies_when_ai_client_not_configured(monkeypatch):
    monkeypatch.setattr(handlers, "get_ai_client", lambda: None)
    update = _update_with_voice()
    context = _context()

    await handlers.handle_voice_message(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "не настроен" in update.message.reply_text.await_args.args[0]
    context.bot.get_file.assert_not_called()


async def test_voice_rejects_too_long_message(monkeypatch):
    monkeypatch.setattr(handlers, "get_ai_client", lambda: AsyncMock())
    monkeypatch.setattr(
        handlers, "get_settings", lambda: Settings(voice_max_duration_seconds=60)
    )
    update = _update_with_voice(duration=61)
    context = _context()

    await handlers.handle_voice_message(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "длиннее" in update.message.reply_text.await_args.args[0]
    context.bot.get_file.assert_not_called()


async def test_voice_replies_when_transcription_fails(monkeypatch):
    ai_client = AsyncMock()
    ai_client.transcribe.side_effect = AIServiceError("boom")
    monkeypatch.setattr(handlers, "get_ai_client", lambda: ai_client)
    monkeypatch.setattr(
        handlers, "get_settings", lambda: Settings(voice_max_duration_seconds=300)
    )
    update = _update_with_voice()
    context = _context()

    await handlers.handle_voice_message(update, context)

    assert "распознать" in update.message.reply_text.await_args.args[0]


async def test_voice_replies_when_transcription_is_empty(monkeypatch):
    ai_client = AsyncMock()
    ai_client.transcribe.return_value = "   "
    monkeypatch.setattr(handlers, "get_ai_client", lambda: ai_client)
    monkeypatch.setattr(
        handlers, "get_settings", lambda: Settings(voice_max_duration_seconds=300)
    )
    update = _update_with_voice()
    context = _context()

    await handlers.handle_voice_message(update, context)

    assert "Не расслышал" in update.message.reply_text.await_args.args[0]


async def test_voice_echoes_transcript_and_routes_it(monkeypatch):
    """Успешная транскрипция: пользователь видит распознанный текст ДО
    ответа движка, а сам текст уходит в тот же роутер, что и обычное
    текстовое сообщение (_route_parsed_text)."""
    ai_client = AsyncMock()
    ai_client.transcribe.return_value = "купить молоко завтра"
    monkeypatch.setattr(handlers, "get_ai_client", lambda: ai_client)
    monkeypatch.setattr(
        handlers, "get_settings", lambda: Settings(voice_max_duration_seconds=300)
    )
    route_spy = AsyncMock()
    monkeypatch.setattr(handlers, "_route_parsed_text", route_spy)
    update = _update_with_voice()
    context = _context()

    await handlers.handle_voice_message(update, context)

    echoed = update.message.reply_text.await_args_list[0].args[0]
    assert "купить молоко завтра" in echoed
    route_spy.assert_awaited_once_with(update, context, "купить молоко завтра")


@pytest.mark.parametrize(
    "text, expected_keyboard_fn",
    [
        ("покажи задачи", "_send_tasks_keyboard"),
        ("привычки", "_send_habits_keyboard"),
        ("что посмотреть", "_send_watchlist_keyboard"),
    ],
)
async def test_route_parsed_text_sends_keyboard_for_list_intents(
    monkeypatch, text, expected_keyboard_fn
):
    spies = {
        name: AsyncMock()
        for name in (
            "_send_tasks_keyboard",
            "_send_habits_keyboard",
            "_send_watchlist_keyboard",
        )
    }
    for name, spy in spies.items():
        monkeypatch.setattr(handlers, name, spy)
    reply_spy = AsyncMock()
    monkeypatch.setattr(handlers, "_reply_via_engine", reply_spy)
    update = MagicMock()
    context = MagicMock()

    await handlers._route_parsed_text(update, context, text)

    spies[expected_keyboard_fn].assert_awaited_once_with(update)
    for name, spy in spies.items():
        if name != expected_keyboard_fn:
            spy.assert_not_called()
    reply_spy.assert_not_called()


async def test_route_parsed_text_falls_back_to_engine_for_other_intents(monkeypatch):
    for name in (
        "_send_tasks_keyboard",
        "_send_habits_keyboard",
        "_send_watchlist_keyboard",
    ):
        monkeypatch.setattr(handlers, name, AsyncMock())
    reply_spy = AsyncMock()
    monkeypatch.setattr(handlers, "_reply_via_engine", reply_spy)
    update = MagicMock()
    context = MagicMock()

    await handlers._route_parsed_text(update, context, "Купить молоко завтра")

    reply_spy.assert_awaited_once()
    args = reply_spy.await_args.args
    assert args[:3] == (update, context, "Купить молоко завтра")
