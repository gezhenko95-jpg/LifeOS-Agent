"""
Экраны разделов (полка/дневник/дайджест) и ожидание ввода после кнопки —
см. specs/014-menu-navigation.md.

Три уровня проверяются отдельно: чистые построители экранов
(keyboards.py), обработка нажатий (callbacks.py) и «следующее сообщение —
это ответ на кнопку» (handlers.py + pending_input.py).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.digest.models import Digest, DigestChannel
from app.digest.scraper import ChannelScrapeError
from app.goals.models import Goal
from app.habits.models import Habit
from app.memory.models import MemoryEntry
from app.tasks.models import Task
from app.telegram import callbacks, handlers, pending_input
from app.telegram.keyboards import (
    MENU_DIGEST,
    MENU_GOALS,
    MENU_HABITS,
    MENU_JOURNAL,
    MENU_TASKS,
    MENU_WATCHLIST,
    build_digest_detail_message,
    build_digest_menu_message,
    build_goals_menu,
    build_goals_message,
    build_habits_menu,
    build_habits_message,
    build_journal_entries_message,
    build_journal_entry_message,
    build_journal_menu,
    build_tasks_menu,
    build_tasks_message,
    build_watchlist_menu,
    build_watchlist_message,
)
from app.watchlist.models import WatchlistItem

OWNER = 414825951


def _task(task_id: int) -> Task:
    return Task(
        id=task_id,
        telegram_user_id=OWNER,
        title="Купить молоко",
        status="active",
        priority="normal",
    )


def _habit(habit_id: int) -> Habit:
    return Habit(id=habit_id, telegram_user_id=OWNER, title="Чтение", archived=False)


def _goal(goal_id: int) -> Goal:
    return Goal(
        id=goal_id,
        telegram_user_id=OWNER,
        title="Выучить испанский",
        progress=40,
        status="active",
    )


def _watchlist_item(item_id: int) -> WatchlistItem:
    return WatchlistItem(
        id=item_id,
        telegram_user_id=OWNER,
        title="Дюна",
        media_type="movie",
        status="to_watch",
    )


def _entry(entry_id: int, content: str = "Хороший день") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        telegram_user_id=OWNER,
        type="journal",
        content=content,
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )


def _callback_data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# --- Построители экранов --------------------------------------------------


def test_watchlist_menu_offers_open_and_add():
    _, markup = build_watchlist_menu()

    assert _callback_data(markup) == ["w|l", "w|n"]


@pytest.mark.parametrize(
    "builder, domain",
    [
        (build_tasks_menu, "t"),
        (build_habits_menu, "h"),
        (build_goals_menu, "g"),
        (build_journal_menu, "j"),
        (build_watchlist_menu, "w"),
    ],
)
def test_every_section_screen_starts_with_list_and_add(builder, domain):
    """Главное правило раздела: первый ряд — всегда «открыть список» и
    «добавить», в том же порядке, с тем же смыслом кода действия."""
    _, markup = builder()

    assert _callback_data(markup)[:2] == [f"{domain}|l", f"{domain}|n"]


@pytest.mark.parametrize(
    "screen, domain",
    [
        (lambda: build_tasks_message([_task(1)]), "t"),
        (lambda: build_habits_message([_habit(1)], {1: 3}), "h"),
        (lambda: build_goals_message([_goal(1)]), "g"),
        (lambda: build_watchlist_message([_watchlist_item(1)]), "w"),
        (lambda: build_journal_entries_message([_entry(1)]), "j"),
    ],
)
def test_every_list_can_go_back_to_its_section(screen, domain):
    _, markup = screen()

    assert _callback_data(markup)[-1] == f"{domain}|m"


def test_journal_menu_offers_read_search_and_write():
    _, markup = build_journal_menu()

    assert _callback_data(markup) == ["j|l", "j|n", "j|f"]


def test_journal_entries_show_date_and_preview():
    text, markup = build_journal_entries_message(
        [_entry(7, "Сегодня был длинный день")]
    )

    assert "20.08" in text
    assert "длинный день" in text
    assert "j|o|7" in _callback_data(markup)


def test_journal_entries_long_text_is_cut_to_preview():
    text, _ = build_journal_entries_message([_entry(1, "я" * 200)])

    assert "…" in text
    assert "я" * 200 not in text


def test_journal_entries_empty_still_offers_way_back():
    text, markup = build_journal_entries_message([])

    assert "пока нет" in text
    assert _callback_data(markup) == ["j|m"]


def test_journal_entry_escapes_html():
    """Запись с угловыми скобками не должна ломать разметку сообщения."""
    text, _ = build_journal_entry_message(_entry(1, "<b>жирно</b>"))

    assert "&lt;b&gt;" in text


def test_digest_menu_lists_digests_and_offers_new():
    digests = [Digest(id=3, telegram_user_id=OWNER, name="ESG", auto_frequency="daily")]

    text, markup = build_digest_menu_message(digests)

    assert "ESG" in text and "каждый день" in text
    assert _callback_data(markup) == ["d|s|3", "d|n"]


def test_digest_menu_when_empty_explains_what_it_is():
    text, markup = build_digest_menu_message([])

    assert "публичных" in text
    assert _callback_data(markup) == ["d|n"]


def test_digest_detail_lists_channels_with_remove_buttons():
    digest = Digest(id=3, telegram_user_id=OWNER, name="ESG")
    channels = [DigestChannel(id=11, digest_id=3, channel_username="durov")]

    text, markup = build_digest_detail_message(digest, channels)

    assert "@durov" in text
    assert _callback_data(markup) == ["d|r|3", "d|a|3", "d|x|11", "d|m"]


def test_digest_detail_without_channels_has_no_remove_buttons():
    digest = Digest(id=3, telegram_user_id=OWNER, name="ESG")

    text, markup = build_digest_detail_message(digest, [])

    assert "Каналов пока нет" in text
    assert _callback_data(markup) == ["d|r|3", "d|a|3", "d|m"]


# --- Нажатия кнопок -------------------------------------------------------


def _context() -> MagicMock:
    context = MagicMock()
    context.user_data = {}
    context.bot.send_chat_action = AsyncMock()
    return context


def _query() -> MagicMock:
    query = MagicMock()
    query.get_bot.return_value.send_chat_action = AsyncMock()
    return query


@pytest.fixture
def digest_service(monkeypatch) -> AsyncMock:
    service = AsyncMock()
    monkeypatch.setattr(callbacks, "build_digest_service", lambda session: service)
    return service


@pytest.fixture
def memory_service(monkeypatch) -> AsyncMock:
    service = AsyncMock()
    monkeypatch.setattr(callbacks, "MemoryService", lambda repository: service)
    monkeypatch.setattr(callbacks, "MemoryRepository", MagicMock())
    return service


async def test_journal_list_action_shows_entries(memory_service):
    memory_service.list_entries.return_value = [_entry(7)]

    text, markup = await callbacks._handle_journal_action(
        MagicMock(), "l", "", OWNER, _context()
    )

    assert "j|o|7" in _callback_data(markup)


async def test_journal_open_action_shows_full_entry(memory_service):
    memory_service.get_entry.return_value = _entry(7, "полный текст записи")

    text, _ = await callbacks._handle_journal_action(
        MagicMock(), "o", "7", OWNER, _context()
    )

    assert "полный текст записи" in text


async def test_journal_open_action_when_entry_is_gone(memory_service):
    memory_service.get_entry.return_value = None

    text, _ = await callbacks._handle_journal_action(
        MagicMock(), "o", "7", OWNER, _context()
    )

    assert "больше нет" in text


async def test_journal_search_action_waits_for_topic():
    context = _context()

    text, _ = await callbacks._handle_journal_action(
        MagicMock(), "f", "", OWNER, context
    )

    assert "найти" in text.lower()
    assert (
        pending_input.pop_pending(context.user_data).kind
        == pending_input.JOURNAL_SEARCH
    )


async def test_digest_add_channel_action_remembers_which_digest(digest_service):
    digest_service.get_digest.return_value = Digest(
        id=3, telegram_user_id=OWNER, name="ESG"
    )
    context = _context()

    text, _ = await callbacks._handle_digest_action(
        MagicMock(), "a", "3", OWNER, context, _query()
    )

    pending = pending_input.pop_pending(context.user_data)
    assert pending.kind == pending_input.DIGEST_CHANNEL
    assert pending.digest_id == 3


async def test_digest_now_action_reports_empty_without_losing_screen(digest_service):
    digest = Digest(id=3, telegram_user_id=OWNER, name="ESG")
    digest_service.get_digest.return_value = digest
    digest_service.build_digest_text.return_value = None
    digest_service.list_channels.return_value = []

    text, markup = await callbacks._handle_digest_action(
        MagicMock(), "r", "3", OWNER, _context(), _query()
    )

    assert "Новых постов пока нет" in text
    # Экран дайджеста остаётся под сообщением — не тупик без кнопок.
    assert "d|m" in _callback_data(markup)


async def test_digest_now_action_escapes_summary(digest_service):
    """Саммари приходит от модели как обычный текст: <угловые скобки> из
    поста не должны ломать parse_mode=HTML."""
    digest_service.get_digest.return_value = Digest(
        id=3, telegram_user_id=OWNER, name="ESG"
    )
    digest_service.build_digest_text.return_value = "новость про <TAG>"

    text, _ = await callbacks._handle_digest_action(
        MagicMock(), "r", "3", OWNER, _context(), _query()
    )

    assert "&lt;TAG&gt;" in text


async def test_digest_remove_channel_action_redraws_digest(digest_service):
    digest = Digest(id=3, telegram_user_id=OWNER, name="ESG")
    digest_service.remove_channel_by_id.return_value = digest
    digest_service.list_channels.return_value = []

    text, markup = await callbacks._handle_digest_action(
        MagicMock(), "x", "11", OWNER, _context(), _query()
    )

    assert "ESG" in text
    digest_service.remove_channel_by_id.assert_awaited_once_with(OWNER, 11)


async def test_digest_action_on_foreign_digest_says_nothing_about_it(digest_service):
    """Чужой id неотличим от несуществующего — тот же принцип, что у
    owned_or_none во всех сервисах."""
    digest_service.get_digest.return_value = None

    text, _ = await callbacks._handle_digest_action(
        MagicMock(), "s", "3", OWNER, _context(), _query()
    )

    assert "больше нет" in text


# --- Ожидание ввода после кнопки ------------------------------------------


def _update() -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = ""
    update.message.reply_text = AsyncMock()
    update.effective_user = SimpleNamespace(id=OWNER)
    return update


def _reply(update: MagicMock) -> str:
    return update.message.reply_text.await_args.args[0]


@pytest.fixture
def no_db(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "AsyncSessionLocal", MagicMock())


async def test_watchlist_pending_accepts_bare_title(no_db, monkeypatch):
    """Кнопка уже сказала, куда добавляем, — префикс «фильм»/«книга» не
    обязателен."""
    service = AsyncMock()
    # Реальная запись всегда имеет поля карточки (миграция 016) — фейк
    # должен быть той же формы, иначе тест разойдётся с продом.
    service.create_item.return_value = _watchlist_item(1)
    monkeypatch.setattr(handlers, "WatchlistService", lambda repository: service)
    monkeypatch.setattr(handlers, "WatchlistRepository", MagicMock())

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.WATCHLIST_ADD)
    )

    handled = await handlers._consume_pending_input(update, context, "Дюна")

    assert handled is True
    service.create_item.assert_awaited_once_with(
        OWNER, "Дюна", "other", tmdb_client=None
    )


async def test_watchlist_pending_keeps_media_type_when_written(no_db, monkeypatch):
    service = AsyncMock()
    service.create_item.return_value = _watchlist_item(1)
    monkeypatch.setattr(handlers, "WatchlistService", lambda repository: service)
    monkeypatch.setattr(handlers, "WatchlistRepository", MagicMock())

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.WATCHLIST_ADD)
    )

    await handlers._consume_pending_input(update, context, "книга Дюна")

    service.create_item.assert_awaited_once_with(
        OWNER, "Дюна", "book", tmdb_client=None
    )


async def test_digest_channel_pending_reports_unknown_channel(no_db, monkeypatch):
    service = AsyncMock()
    service.get_digest.return_value = Digest(id=3, telegram_user_id=OWNER, name="ESG")
    service.add_channel.side_effect = ChannelScrapeError("не найден")
    monkeypatch.setattr(handlers, "build_digest_service", lambda session: service)

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data,
        pending_input.PendingInput(pending_input.DIGEST_CHANNEL, digest_id=3),
    )

    await handlers._consume_pending_input(update, context, "nosuch")

    assert "Не нашёл канал" in _reply(update)


async def test_pending_is_one_shot_even_after_failure(no_db, monkeypatch):
    """Неудачная попытка не должна оставлять ловушку: следующая обычная
    фраза уже не считается ответом на кнопку."""
    service = AsyncMock()
    service.get_digest.return_value = Digest(id=3, telegram_user_id=OWNER, name="ESG")
    service.add_channel.side_effect = ChannelScrapeError("не найден")
    monkeypatch.setattr(handlers, "build_digest_service", lambda session: service)

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data,
        pending_input.PendingInput(pending_input.DIGEST_CHANNEL, digest_id=3),
    )

    await handlers._consume_pending_input(update, context, "nosuch")
    handled_again = await handlers._consume_pending_input(
        update, context, "купить хлеб"
    )

    assert handled_again is False


async def test_habit_pending_takes_whole_text_as_title(no_db, monkeypatch):
    """Слово «привычка» в начале фразы (как требует текстовый путь) после
    кнопки не нужно — кнопка уже сказала, что это привычка."""
    service = AsyncMock()
    service.create_habit.return_value = SimpleNamespace(title="зарядка")
    monkeypatch.setattr(handlers, "HabitService", lambda repository: service)
    monkeypatch.setattr(handlers, "HabitRepository", MagicMock())

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.HABIT_ADD)
    )

    await handlers._consume_pending_input(update, context, "зарядка")

    service.create_habit.assert_awaited_once_with(OWNER, "зарядка")


async def test_goal_pending_creates_goal_without_asking_for_date(no_db, monkeypatch):
    service = AsyncMock()
    service.create_goal.return_value = SimpleNamespace(title="пробежать 10 км")
    monkeypatch.setattr(handlers, "GoalService", lambda repository: service)
    monkeypatch.setattr(handlers, "GoalRepository", MagicMock())

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.GOAL_ADD)
    )

    await handlers._consume_pending_input(update, context, "пробежать 10 км")

    service.create_goal.assert_awaited_once_with(OWNER, "пробежать 10 км")


async def test_task_pending_still_goes_through_engine(no_db, monkeypatch):
    """У задачи в тексте может быть срок («завтра в 19:00») — разбирать
    его заново в обход движка значило бы завести второй парсер дат."""
    route = AsyncMock()
    monkeypatch.setattr(handlers, "_reply_via_engine", route)

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.TASK_ADD)
    )

    handled = await handlers._consume_pending_input(
        update, context, "завтра в 19:00 позвонить маме"
    )

    assert handled is True
    route.assert_awaited_once_with(update, context, "завтра в 19:00 позвонить маме")


async def test_digest_new_pending_parses_name_and_frequency(no_db, monkeypatch):
    service = AsyncMock()
    service.create_digest.return_value = Digest(
        id=3, telegram_user_id=OWNER, name="ESG", auto_frequency="daily"
    )
    service.list_digests.return_value = []
    monkeypatch.setattr(handlers, "build_digest_service", lambda session: service)

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.DIGEST_NEW)
    )

    await handlers._consume_pending_input(update, context, "ESG daily")

    service.create_digest.assert_awaited_once_with(OWNER, "ESG", "daily")


async def test_digest_new_pending_rejects_multiword_name(no_db, monkeypatch):
    service = AsyncMock()
    monkeypatch.setattr(handlers, "build_digest_service", lambda session: service)

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.DIGEST_NEW)
    )

    await handlers._consume_pending_input(update, context, "моя большая тема каналов")

    assert "одним словом" in _reply(update)
    service.create_digest.assert_not_awaited()


async def test_journal_search_pending_searches_journal_only(no_db, monkeypatch):
    service = AsyncMock()
    service.search.return_value = []
    monkeypatch.setattr(handlers, "MemoryService", lambda repository: service)
    monkeypatch.setattr(handlers, "MemoryRepository", MagicMock())

    update, context = _update(), _context()
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.JOURNAL_SEARCH)
    )

    await handlers._consume_pending_input(update, context, "работа")

    assert service.search.await_args.kwargs["type"].value == "journal"


async def test_no_pending_means_normal_routing(no_db):
    handled = await handlers._consume_pending_input(
        _update(), _context(), "купить хлеб"
    )

    assert handled is False


@pytest.mark.parametrize(
    "button, sender",
    [
        (MENU_TASKS, "_send_section"),
        (MENU_HABITS, "_send_section"),
        (MENU_GOALS, "_send_section"),
        (MENU_WATCHLIST, "_send_section"),
        (MENU_JOURNAL, "_send_section"),
        (MENU_DIGEST, "_send_digest_menu"),
    ],
)
async def test_menu_buttons_open_section_screens(monkeypatch, button, sender):
    """Ни одна кнопка домена не делает действие сразу — все шесть
    открывают экран раздела."""
    called = AsyncMock()
    monkeypatch.setattr(handlers, sender, called)
    update, context = _update(), _context()
    update.message.text = button

    await handlers.handle_text_message(update, context)

    called.assert_awaited_once()


async def test_menu_button_cancels_pending_input(monkeypatch):
    """Ушли в другой раздел — ожидание ввода снимается, иначе оно
    проглотило бы следующее сообщение совсем на другую тему."""
    monkeypatch.setattr(handlers, "_send_digest_menu", AsyncMock())
    update, context = _update(), _context()
    update.message.text = MENU_DIGEST
    pending_input.set_pending(
        context.user_data, pending_input.PendingInput(pending_input.WATCHLIST_ADD)
    )

    await handlers.handle_text_message(update, context)

    assert pending_input.pop_pending(context.user_data) is None
