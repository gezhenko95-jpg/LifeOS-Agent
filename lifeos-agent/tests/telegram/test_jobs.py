"""
app/telegram/jobs.py — джобы планировщика. `AsyncSessionLocal` мокается
целиком (тот же приём, что `no_db` в test_menu_navigation.py), сервисы
подменяются на AsyncMock с готовыми возвратами — реальная БД не нужна.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.digest.models import Digest
from app.telegram import jobs


@pytest.fixture
def no_db(monkeypatch) -> None:
    monkeypatch.setattr(jobs, "AsyncSessionLocal", MagicMock())


def _context() -> MagicMock:
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


def _owner_settings() -> MagicMock:
    return MagicMock(owner_telegram_user_id=1)


async def test_send_digests_job_attaches_save_button(no_db, monkeypatch):
    """specs/016-engagement-hooks.md: под каждым дайджестом — кнопка
    "⭐ Сохранить" с id темы в callback_data (см. app/telegram/callbacks.py
    ::_handle_digest_action, action "f")."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    digest = Digest(id=7, telegram_user_id=1, name="ESG", auto_frequency="daily")
    service = AsyncMock()
    service.list_digests.return_value = [digest]
    service.build_digest_text.return_value = "Свежие новости ESG."
    monkeypatch.setattr(jobs, "build_digest_service", lambda session: service)

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Свежие новости ESG."
    markup = kwargs["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ["d|f|7"]


async def test_send_digests_job_skips_when_no_new_posts(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    digest = Digest(id=7, telegram_user_id=1, name="ESG", auto_frequency="daily")
    service = AsyncMock()
    service.list_digests.return_value = [digest]
    service.build_digest_text.return_value = None
    monkeypatch.setattr(jobs, "build_digest_service", lambda session: service)

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_send_digests_job_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_digests_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_morning_briefing_appends_reflection_question(no_db, monkeypatch):
    """specs/016-engagement-hooks.md: утренняя рефлексия (раньше —
    отдельная джоба в отдельном слоте) теперь дописывается снизу к
    брифингу — один push вместо двух."""
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    monkeypatch.setattr(
        jobs, "build_morning_briefing", AsyncMock(return_value="Доброе утро!")
    )
    monkeypatch.setattr(jobs, "_try_build_chart", AsyncMock(return_value=None))
    prompt_service = AsyncMock()
    prompt_service.pick_morning_reflection.return_value = "Что тебе снилось?"
    monkeypatch.setattr(jobs, "build_prompt_service", lambda session: prompt_service)

    context = _context()
    await jobs.send_morning_briefing_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Доброе утро!\n\nЧто тебе снилось?"
    prompt_service.pick_morning_reflection.assert_awaited_once_with(1, allow_gap=False)


async def test_morning_briefing_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_morning_briefing_job(context)

    context.bot.send_message.assert_not_awaited()


async def test_send_finance_report_job_sends_report(no_db, monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", _owner_settings)
    monkeypatch.setattr(jobs, "get_ai_client", lambda settings: None)
    monkeypatch.setattr(
        jobs, "build_finance_report", AsyncMock(return_value="Финансы за август")
    )
    monkeypatch.setattr(jobs, "build_finance_service", lambda session: AsyncMock())

    context = _context()
    await jobs.send_finance_report_job(context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert kwargs["text"] == "Финансы за август"


async def test_send_finance_report_job_no_owner_does_nothing(monkeypatch):
    monkeypatch.setattr(
        jobs, "get_settings", lambda: MagicMock(owner_telegram_user_id=0)
    )

    context = _context()
    await jobs.send_finance_report_job(context)

    context.bot.send_message.assert_not_awaited()
