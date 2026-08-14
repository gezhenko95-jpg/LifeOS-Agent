from datetime import datetime

from app.goals.models import Goal
from app.habits.models import Habit
from app.tasks.models import Task
from app.telegram.keyboards import (
    MENU_ADD_TASK,
    MENU_GOALS,
    MENU_HABITS,
    MENU_HELP,
    MENU_INSIGHTS,
    MENU_JOURNAL,
    MENU_SITE,
    MENU_TASKS,
    MENU_WATCHLIST,
    build_goals_message,
    build_habits_message,
    build_main_menu,
    build_open_site_keyboard,
    build_task_confirmation_message,
    build_task_quick_actions_keyboard,
    build_tasks_message,
    build_watchlist_message,
)
from app.watchlist.models import WatchlistItem


def _task(id_, title="Купить молоко", priority="normal", due_date=None) -> Task:
    return Task(
        id=id_, telegram_user_id=1, title=title, priority=priority, due_date=due_date
    )


def _habit(id_, title="Читать") -> Habit:
    return Habit(id=id_, telegram_user_id=1, title=title)


def _goal(id_, title="Выучить английский", progress=0) -> Goal:
    return Goal(id=id_, telegram_user_id=1, title=title, progress=progress)


def _item(id_, title="Дюна", media_type="movie") -> WatchlistItem:
    return WatchlistItem(
        id=id_,
        telegram_user_id=1,
        title=title,
        media_type=media_type,
        status="to_watch",
        source="manual",
    )


def _callback_data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# --- Задачи ---------------------------------------------------------------


def test_tasks_message_empty():
    text, markup = build_tasks_message([])

    assert "Пусто" in text
    assert len(markup.inline_keyboard) == 0


def test_tasks_message_shows_title_in_text_not_only_in_buttons():
    """Раньше список жил в подписях кнопок и обрезался по 45 символов.
    Теперь содержимое — в тексте, кнопки только нумерованные действия."""
    text, markup = build_tasks_message([_task(1)])

    assert "Купить молоко" in text
    assert _callback_data(markup) == ["t|c|1", "t|d|1"]
    assert [b.text for row in markup.inline_keyboard for b in row] == ["✅ 1", "🗑 1"]


def test_tasks_message_numbers_match_between_text_and_buttons():
    text, markup = build_tasks_message([_task(7), _task(8, title="Позвонить")])

    assert "<b>1</b>" in text and "<b>2</b>" in text
    assert _callback_data(markup) == ["t|c|7", "t|c|8", "t|d|7", "t|d|8"]


def test_tasks_message_high_priority_marker():
    text, _ = build_tasks_message([_task(1, priority="high")])

    assert "❗" in text


def test_tasks_message_shows_human_due_date():
    text, _ = build_tasks_message([_task(1, due_date=datetime(2026, 8, 20, 9, 0))])

    assert "20.08" in text or "в 09:00" in text


def test_tasks_message_marks_overdue_in_summary():
    text, _ = build_tasks_message([_task(1, due_date=datetime(2020, 1, 1, 9, 0))])

    assert "просроч" in text


def test_tasks_message_caps_at_max_items_but_says_so():
    """Лишние задачи раньше молча не показывались, и пользователь считал,
    что их нет."""
    text, markup = build_tasks_message([_task(i) for i in range(1, 15)])

    assert len(_callback_data(markup)) == 20  # 10 задач × 2 действия
    assert "ещё 4" in text


def test_task_title_is_html_escaped():
    """Задача с названием «<b>» иначе сломала бы разметку сообщения."""
    text, _ = build_tasks_message([_task(1, title="<b>взлом</b>")])

    assert "&lt;b&gt;взлом&lt;/b&gt;" in text


# --- Быстрые кнопки под подтверждением ------------------------------------


def test_quick_actions_both_buttons_when_nothing_set():
    markup = build_task_quick_actions_keyboard(_task(1))

    assert _callback_data(markup) == ["t|p|1", "t|w|1"]


def test_quick_actions_omits_priority_button_when_already_high():
    markup = build_task_quick_actions_keyboard(_task(1, priority="high"))

    assert _callback_data(markup) == ["t|w|1"]


def test_quick_actions_omits_date_button_when_already_set():
    markup = build_task_quick_actions_keyboard(
        _task(1, due_date=datetime(2026, 8, 20, 9, 0))
    )

    assert _callback_data(markup) == ["t|p|1"]


def test_quick_actions_none_when_both_already_set():
    markup = build_task_quick_actions_keyboard(
        _task(1, priority="high", due_date=datetime(2026, 8, 20, 9, 0))
    )

    assert markup is None


def test_task_confirmation_message_reflects_state():
    text, _ = build_task_confirmation_message(
        _task(1, priority="high", due_date=datetime(2026, 8, 20, 9, 0))
    )

    assert "❗" in text
    assert "Купить молоко" in text


# --- Привычки -------------------------------------------------------------


def test_habits_message_empty():
    text, markup = build_habits_message([], {})

    assert "ни одной" in text.lower()
    assert len(markup.inline_keyboard) == 0


def test_habits_message_with_streak_shows_bar():
    text, markup = build_habits_message([_habit(1)], {1: 12})

    assert "Читать" in text
    assert "🔥 12" in text
    assert "▓" in text
    assert _callback_data(markup) == ["h|d|1", "h|x|1"]


def test_habits_message_without_streak_invites_to_start():
    text, _ = build_habits_message([_habit(1)], {1: 0})

    assert "🔥" not in text
    assert "начать" in text


# --- Цели -----------------------------------------------------------------


def test_goals_message_empty():
    text, markup = build_goals_message([])

    assert "Ни одной" in text
    assert len(markup.inline_keyboard) == 0


def test_goals_message_shows_progress_bar_and_actions():
    text, markup = build_goals_message([_goal(1, progress=60)])

    assert "Выучить английский" in text
    assert "▓" in text and "60%" in text
    assert _callback_data(markup) == ["g|noop", "g|n|1", "g|u|1", "g|c|1", "g|x|1"]


def test_goals_message_shows_average_progress():
    text, _ = build_goals_message([_goal(1, progress=40), _goal(2, progress=60)])

    assert "50%" in text


# --- Меню и watchlist -----------------------------------------------------


def test_main_menu_has_expected_buttons_in_rows():
    markup = build_main_menu()
    labels = [[b.text for b in row] for row in markup.keyboard]

    assert labels == [
        [MENU_TASKS],
        [MENU_HABITS, MENU_GOALS],
        [MENU_ADD_TASK, MENU_JOURNAL],
        [MENU_INSIGHTS, MENU_WATCHLIST],
        [MENU_SITE, MENU_HELP],
    ]


def test_main_menu_resizes_to_fit():
    assert build_main_menu().resize_keyboard is True


def test_watchlist_message_empty():
    text, markup = build_watchlist_message([])

    assert "пуст" in text.lower()
    assert len(markup.inline_keyboard) == 0


def test_watchlist_message_shows_items_and_recommend_button():
    text, markup = build_watchlist_message([_item(1, "Дюна")])

    assert "Дюна" in text
    assert "w|r|0" in _callback_data(markup)


def test_watchlist_message_shows_media_emoji():
    text, _ = build_watchlist_message(
        [_item(1, "Дюна", "movie"), _item(2, "Идиот", "book")]
    )

    assert "🎬" in text and "📖" in text


def test_watchlist_message_caps_at_max_items():
    _, markup = build_watchlist_message([_item(i, f"Ф{i}") for i in range(1, 15)])

    # 10 записей × 2 действия + кнопка «Порекомендуй»
    assert len(_callback_data(markup)) == 21


def test_open_site_keyboard_has_url_button():
    markup = build_open_site_keyboard("https://lifeos-agent.ru/ui")

    assert markup.inline_keyboard[0][0].url == "https://lifeos-agent.ru/ui"
