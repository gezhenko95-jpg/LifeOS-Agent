"""
Команды дайджестов — первые в проекте команды с аргументами
(context.args). Проверяем разбор args и ветвление ответов, без реального
Telegram/БД (по образцу tests/telegram/test_voice.py).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.digest.models import Digest, DigestChannel
from app.digest.scraper import ChannelScrapeError
from app.telegram import handlers


def _update() -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = SimpleNamespace(id=414825951)
    return update


def _context(args: list[str] | None = None) -> MagicMock:
    context = MagicMock()
    context.args = args
    context.bot.send_chat_action = AsyncMock()
    return context


@pytest.fixture
def service(monkeypatch) -> AsyncMock:
    """Подменяем и фабрику сервиса, и сессию БД — сюда тесты не ходят."""
    service = AsyncMock()
    monkeypatch.setattr(handlers, "build_digest_service", lambda session: service)
    monkeypatch.setattr(handlers, "AsyncSessionLocal", MagicMock())
    return service


def _reply(update: MagicMock) -> str:
    return update.message.reply_text.await_args.args[0]


@pytest.mark.parametrize(
    "command, args",
    [
        ("digest_new_command", []),
        ("digest_new_command", ["ESG", "daily", "лишнее"]),
        ("digest_add_command", ["ESG"]),
        ("digest_remove_command", ["ESG"]),
        ("digest_now_command", []),
        ("digest_now_command", ["ESG", "лишнее"]),
    ],
)
async def test_wrong_arity_replies_with_usage(service, command, args):
    update = _update()

    await getattr(handlers, command)(update, _context(args))

    assert "Как это работает" in _reply(update)
    service.assert_not_awaited()


async def test_digest_new_creates_digest(service):
    service.create_digest.return_value = Digest(
        telegram_user_id=1, name="ESG", auto_frequency="daily"
    )
    update = _update()

    await handlers.digest_new_command(update, _context(["ESG", "daily"]))

    service.create_digest.assert_awaited_once_with(414825951, "ESG", "daily")
    assert "ESG" in _reply(update)


async def test_digest_new_without_frequency_passes_none(service):
    service.create_digest.return_value = Digest(telegram_user_id=1, name="ESG")
    update = _update()

    await handlers.digest_new_command(update, _context(["ESG"]))

    service.create_digest.assert_awaited_once_with(414825951, "ESG", None)
    assert "по запросу" in _reply(update)


async def test_digest_new_reports_validation_error(service):
    service.create_digest.side_effect = ValueError("Дайджест «ESG» уже есть")
    update = _update()

    await handlers.digest_new_command(update, _context(["ESG"]))

    assert "уже есть" in _reply(update)


async def test_digest_add_reports_unknown_channel(service):
    service.add_channel.side_effect = ChannelScrapeError("не найден")
    update = _update()

    await handlers.digest_add_command(update, _context(["ESG", "nosuch"]))

    assert "Не нашёл канал" in _reply(update)


async def test_digest_add_confirms(service):
    service.add_channel.return_value = DigestChannel(
        id=1, digest_id=7, channel_username="telegram"
    )
    update = _update()

    await handlers.digest_add_command(update, _context(["ESG", "@telegram"]))

    service.add_channel.assert_awaited_once_with(414825951, "ESG", "@telegram")
    assert "@telegram" in _reply(update)


async def test_digest_remove_when_channel_absent(service):
    service.remove_channel.return_value = False
    update = _update()

    await handlers.digest_remove_command(update, _context(["ESG", "telegram"]))

    assert "и не было" in _reply(update)


async def test_digest_list_when_empty(service):
    service.list_digests.return_value = []
    update = _update()

    await handlers.digest_list_command(update, _context())

    assert "Пока ни одного дайджеста" in _reply(update)


async def test_digest_list_shows_channels_and_schedule(service):
    service.list_digests.return_value = [
        Digest(id=7, telegram_user_id=1, name="ESG", auto_frequency="weekly")
    ]
    service.list_channels.return_value = [
        DigestChannel(id=1, digest_id=7, channel_username="telegram")
    ]
    update = _update()

    await handlers.digest_list_command(update, _context())

    reply = _reply(update)
    assert "ESG" in reply
    assert "по воскресеньям" in reply
    assert "@telegram" in reply


async def test_digest_now_sends_text(service, monkeypatch):
    monkeypatch.setattr(handlers, "get_ai_client", lambda: None)
    service.build_digest_text.return_value = "📰 Дайджест «ESG»\n\n• пост"
    update = _update()

    await handlers.digest_now_command(update, _context(["ESG"]))

    assert "• пост" in _reply(update)


async def test_digest_now_answers_even_without_new_posts(service, monkeypatch):
    """По запросу отвечаем всегда — в отличие от фоновой job, которая
    тихо пропускает пустой дайджест."""
    monkeypatch.setattr(handlers, "get_ai_client", lambda: None)
    service.build_digest_text.return_value = None
    update = _update()

    await handlers.digest_now_command(update, _context(["ESG"]))

    assert "Новых постов" in _reply(update)


async def test_digest_now_reports_unknown_digest(service, monkeypatch):
    monkeypatch.setattr(handlers, "get_ai_client", lambda: None)
    service.build_digest_text.side_effect = ValueError("Дайджеста «ESG» нет")
    update = _update()

    await handlers.digest_now_command(update, _context(["ESG"]))

    assert "нет" in _reply(update)
