from datetime import datetime, timedelta, timezone

from app.crm.models import Contact
from app.finance.models import EXPENSE, INCOME, Transaction
from app.finance.service import CategoryBreakdown, FinanceSummary
from app.goals.models import Goal
from app.habits.models import Habit
from app.mood.models import MoodEntry
from app.tasks.models import Task
from app.telegram.keyboards import (
    MENU_CONTACTS,
    MENU_DIGEST,
    MENU_FINANCE,
    MENU_GOALS,
    MENU_HABITS,
    MENU_HELP,
    MENU_INSIGHTS,
    MENU_JOURNAL,
    MENU_MOOD,
    MENU_SITE,
    MENU_TASKS,
    MENU_WATCHLIST,
    build_contacts_menu,
    build_contacts_message,
    build_finance_menu,
    build_finance_message,
    build_goals_message,
    build_habits_message,
    build_main_menu,
    build_mood_menu,
    build_mood_message,
    build_mood_prompt_keyboard,
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


def _transaction(id_, kind=EXPENSE, category="transport", amount=500) -> Transaction:
    return Transaction(
        id=id_,
        telegram_user_id=1,
        kind=kind,
        category=category if kind == EXPENSE else None,
        amount=amount,
    )


def _summary(**kwargs) -> FinanceSummary:
    kwargs.setdefault("income_total", 0)
    kwargs.setdefault("mandatory_total", 0)
    kwargs.setdefault("free_money", 0)
    return FinanceSummary(**kwargs)


def _contact(id_, name="Аня", last_contact_at=None, **kwargs) -> Contact:
    return Contact(
        id=id_,
        telegram_user_id=1,
        name=name,
        last_contact_at=last_contact_at or datetime.now(timezone.utc),
        **kwargs,
    )


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
    assert _callback_data(markup) == [
        "t|c|1",
        "t|d|1",
        "t|i|1",
        "t|a|1",
        "t|k|1",
        "t|m",
    ]
    assert [b.text for row in markup.inline_keyboard for b in row] == [
        "✅ 1",
        "🗑 1",
        "▶ 1",
        "📎 1",
        "💬 1",
        "◀️ Назад",
    ]


def test_tasks_message_numbers_match_between_text_and_buttons():
    text, markup = build_tasks_message([_task(7), _task(8, title="Позвонить")])

    assert "<b>1</b>" in text and "<b>2</b>" in text
    assert _callback_data(markup) == [
        "t|c|7",
        "t|c|8",
        "t|d|7",
        "t|d|8",
        "t|i|7",
        "t|i|8",
        "t|a|7",
        "t|a|8",
        "t|k|7",
        "t|k|8",
        "t|m",
    ]


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

    assert len(_callback_data(markup)) == 51  # 10 задач × 5 действий + «Назад»
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
    assert _callback_data(markup) == ["h|d|1", "h|x|1", "h|m"]


def test_habits_message_without_streak_invites_to_start():
    text, _ = build_habits_message([_habit(1)], {1: 0})

    assert "🔥" not in text
    assert "начать" in text


def test_habits_message_caps_at_max_items_but_says_so():
    habits = [_habit(i) for i in range(1, 15)]
    text, markup = build_habits_message(habits, {})

    assert len(_callback_data(markup)) == 21  # 10 × 2 действия + «Назад»
    assert "ещё 4" in text


# --- Цели -----------------------------------------------------------------


def test_goals_message_empty():
    text, markup = build_goals_message([])

    assert "Ни одной" in text
    assert len(markup.inline_keyboard) == 0


def test_goals_message_shows_progress_bar_and_actions():
    text, markup = build_goals_message([_goal(1, progress=60)])

    assert "Выучить английский" in text
    assert "▓" in text and "60%" in text
    assert _callback_data(markup) == [
        "g|noop",
        "g|p|1",
        "g|u|1",
        "g|c|1",
        "g|x|1",
        "g|m",
    ]


def test_goals_message_shows_average_progress():
    text, _ = build_goals_message([_goal(1, progress=40), _goal(2, progress=60)])

    assert "50%" in text


def test_goals_message_caps_at_max_items_but_says_so():
    goals = [_goal(i) for i in range(1, 15)]
    text, _ = build_goals_message(goals)

    assert "ещё 4" in text


# --- Финансы ----------------------------------------------------------


def test_finance_menu_has_two_add_buttons():
    _, markup = build_finance_menu()

    assert _callback_data(markup) == ["f|l", "f|n", "f|i"]


def test_finance_message_empty_shows_hint():
    text, markup = build_finance_message([], _summary())

    assert "Записей пока нет" in text
    assert _callback_data(markup) == ["f|n", "f|i", "f|m"]


def test_finance_message_shows_summary_totals():
    summary = _summary(income_total=80000, mandatory_total=45000, free_money=35000)

    text, _ = build_finance_message([], summary)

    assert "80 000" in text
    assert "45 000" in text
    assert "35 000" in text


def test_finance_message_shows_category_breakdown():
    summary = _summary(
        categories=[
            CategoryBreakdown(
                category="groceries", label="🛒 Продукты", spent=2000, norm=3000
            )
        ]
    )

    text, _ = build_finance_message([], summary)

    assert "🛒 Продукты: 2 000 / 3 000 ₽ нормы" in text
    assert "⚠️" not in text


def test_finance_message_flags_over_budget_category():
    summary = _summary(
        categories=[
            CategoryBreakdown(
                category="eating_out", label="🍔 Кафе", spent=9000, norm=1500
            )
        ]
    )

    text, _ = build_finance_message([], summary)

    assert "⚠️ 🍔 Кафе" in text


def test_finance_message_lists_expense_and_income_transactions():
    transactions = [
        _transaction(1, kind=EXPENSE, category="transport", amount=500),
        _transaction(2, kind=INCOME, amount=80000),
    ]

    text, markup = build_finance_message(transactions, _summary())

    assert "💸 500 ₽ — 🚕 Транспорт" in text
    assert "💰 80 000 ₽ — доход" in text
    assert _callback_data(markup) == ["f|x|1", "f|x|2", "f|n", "f|i", "f|m"]


def test_finance_message_caps_at_max_items_but_says_so():
    """Раньше здесь вообще не было общего числа транзакций в сводке —
    расхождение между «Последние» (10) и реальным количеством было не
    видно совсем, не только необъяснённым."""
    transactions = [_transaction(i) for i in range(1, 15)]
    text, _ = build_finance_message(transactions, _summary())

    assert "ещё 4" in text


# --- Люди / личный CRM ------------------------------------------------


def test_contacts_menu_has_open_and_add_buttons():
    _, markup = build_contacts_menu()

    assert _callback_data(markup) == ["c|l", "c|n"]


def test_contacts_message_empty_shows_hint():
    text, markup = build_contacts_message([])

    assert "Пока никого" in text
    assert _callback_data(markup) == []


def test_contacts_message_orders_stale_first_and_flags_overdue():
    stale = _contact(
        1, "Стас", last_contact_at=datetime.now(timezone.utc) - timedelta(days=31)
    )
    recent = _contact(
        2, "Рита", last_contact_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    text, markup = build_contacts_message([stale, recent])

    assert text.index("Стас") < text.index("Рита")
    assert "⚠️ Стас" in text
    assert "⚠️ Рита" not in text
    assert _callback_data(markup) == ["c|d|1", "c|d|2", "c|x|1", "c|x|2", "c|m"]


def test_contacts_message_shows_birthday_when_set():
    contact = _contact(1, "Петя", birthday_month=9, birthday_day=14)

    text, _ = build_contacts_message([contact])

    assert "🎂 14 сентября" in text


def test_contacts_message_hides_birthday_when_not_set():
    contact = _contact(1, "Аня")

    text, _ = build_contacts_message([contact])

    assert "🎂" not in text


def test_contacts_message_caps_at_max_items_but_says_so():
    contacts = [_contact(i, f"Контакт{i}") for i in range(1, 15)]
    text, _ = build_contacts_message(contacts)

    assert "ещё 4" in text


# --- Настроение -------------------------------------------------------


def _mood_entry(id_, score=3, logged_at=None) -> MoodEntry:
    return MoodEntry(
        id=id_,
        telegram_user_id=1,
        score=score,
        logged_at=logged_at or datetime.now(timezone.utc),
    )


def test_mood_prompt_keyboard_has_five_scores():
    markup = build_mood_prompt_keyboard()

    assert _callback_data(markup) == ["m|s|1", "m|s|2", "m|s|3", "m|s|4", "m|s|5"]


def test_mood_menu_has_scores_and_history_button():
    _, markup = build_mood_menu()

    assert _callback_data(markup) == [
        "m|s|1",
        "m|s|2",
        "m|s|3",
        "m|s|4",
        "m|s|5",
        "m|l",
    ]


def test_mood_message_empty_shows_hint():
    text, markup = build_mood_message([])

    assert "Записей пока нет" in text
    assert _callback_data(markup) == ["m|m"]


def test_mood_message_shows_score_and_emoji():
    text, _ = build_mood_message([_mood_entry(1, score=4)])

    assert "🙂" in text
    assert "4/5" in text


def test_mood_message_caps_at_max_items_but_says_so():
    entries = [_mood_entry(i) for i in range(1, 15)]
    text, _ = build_mood_message(entries)

    assert "ещё 4" in text


# --- Меню и watchlist -----------------------------------------------------


def test_main_menu_has_expected_buttons_in_rows():
    markup = build_main_menu()
    labels = [[b.text for b in row] for row in markup.keyboard]

    assert labels == [
        [MENU_TASKS],
        [MENU_HABITS, MENU_GOALS],
        [MENU_JOURNAL, MENU_WATCHLIST],
        [MENU_DIGEST, MENU_FINANCE],
        [MENU_CONTACTS, MENU_MOOD],
        [MENU_INSIGHTS, MENU_SITE],
        [MENU_HELP],
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


def test_watchlist_message_caps_at_max_items_but_says_so():
    text, markup = build_watchlist_message([_item(i, f"Ф{i}") for i in range(1, 15)])

    # 10 записей × 2 действия + «Порекомендуй», «Добавить» и «Назад»
    assert len(_callback_data(markup)) == 23
    assert "ещё 4" in text


def test_open_site_keyboard_has_url_button():
    markup = build_open_site_keyboard("https://lifeos-agent.ru/ui")

    assert markup.inline_keyboard[0][0].url == "https://lifeos-agent.ru/ui"
