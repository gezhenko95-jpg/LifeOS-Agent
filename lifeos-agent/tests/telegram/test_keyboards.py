from datetime import datetime

from app.goals.models import Goal
from app.habits.models import Habit
from app.tasks.models import Task
from app.telegram.keyboards import (
    MENU_GOALS,
    MENU_HABITS,
    MENU_HELP,
    MENU_TASKS,
    build_goals_message,
    build_habits_message,
    build_main_menu,
    build_task_confirmation_message,
    build_task_quick_actions_keyboard,
    build_tasks_message,
)


def _task(id_, title="Купить молоко", priority="normal", due_date=None) -> Task:
    return Task(
        id=id_, telegram_user_id=1, title=title, priority=priority, due_date=due_date
    )


def _habit(id_, title="Читать") -> Habit:
    return Habit(id=id_, telegram_user_id=1, title=title)


def _goal(id_, title="Выучить английский", progress=0) -> Goal:
    return Goal(id=id_, telegram_user_id=1, title=title, progress=progress)


def test_tasks_message_empty():
    text, markup = build_tasks_message([])

    assert "нет" in text
    assert len(markup.inline_keyboard) == 0


def test_tasks_message_normal_task():
    text, markup = build_tasks_message([_task(1)])

    assert text == "Ваши задачи:"
    row = markup.inline_keyboard[0]
    assert len(row) == 2
    assert "Купить молоко" in row[0].text
    assert row[0].callback_data == "t|c|1"
    assert row[1].callback_data == "t|d|1"
    assert "❗" not in row[0].text


def test_tasks_message_high_priority_marker():
    _, markup = build_tasks_message([_task(1, priority="high")])

    assert "❗" in markup.inline_keyboard[0][0].text


def test_tasks_message_shows_due_date():
    due = datetime(2026, 8, 20, 9, 0)
    _, markup = build_tasks_message([_task(1, due_date=due)])

    assert "20.08" in markup.inline_keyboard[0][0].text


def test_tasks_message_caps_at_max_items():
    tasks = [_task(i) for i in range(1, 15)]

    _, markup = build_tasks_message(tasks)

    assert len(markup.inline_keyboard) == 10


def test_quick_actions_both_buttons_when_nothing_set():
    markup = build_task_quick_actions_keyboard(_task(1))

    row = markup.inline_keyboard[0]
    callbacks = [button.callback_data for button in row]
    assert callbacks == ["t|p|1", "t|w|1"]


def test_quick_actions_omits_priority_button_when_already_high():
    markup = build_task_quick_actions_keyboard(_task(1, priority="high"))

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "t|p|1" not in callbacks
    assert "t|w|1" in callbacks


def test_quick_actions_omits_date_button_when_already_set():
    markup = build_task_quick_actions_keyboard(
        _task(1, due_date=datetime(2026, 8, 20, 9, 0))
    )

    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "t|w|1" not in callbacks
    assert "t|p|1" in callbacks


def test_quick_actions_none_when_both_already_set():
    task = _task(1, priority="high", due_date=datetime(2026, 8, 20, 9, 0))

    assert build_task_quick_actions_keyboard(task) is None


def test_task_confirmation_message_reflects_state():
    task = _task(1, title="Оплатить интернет", priority="high")

    text, markup = build_task_confirmation_message(task)

    assert text == "❗ Добавил задачу: «Оплатить интернет»"
    assert len(markup.inline_keyboard[0]) == 1  # только "Завтра" осталась


def test_habits_message_empty():
    text, markup = build_habits_message([], {})

    assert "нет" in text
    assert len(markup.inline_keyboard) == 0


def test_habits_message_with_streak():
    text, markup = build_habits_message([_habit(1)], {1: 5})

    assert text == "Ваши привычки:"
    row = markup.inline_keyboard[0]
    assert "🔥5" in row[0].text
    assert row[0].callback_data == "h|d|1"
    assert row[1].callback_data == "h|x|1"


def test_habits_message_without_streak_has_no_fire_marker():
    _, markup = build_habits_message([_habit(1)], {1: 0})

    assert "🔥" not in markup.inline_keyboard[0][0].text


def test_goals_message_empty():
    text, markup = build_goals_message([])

    assert "нет" in text
    assert len(markup.inline_keyboard) == 0


def test_goals_message_has_title_row_and_action_row():
    text, markup = build_goals_message([_goal(1, progress=40)])

    assert text == "Ваши цели:"
    assert len(markup.inline_keyboard) == 2

    title_row = markup.inline_keyboard[0]
    assert "40%" in title_row[0].text
    assert title_row[0].callback_data == "g|noop"

    action_row = markup.inline_keyboard[1]
    callbacks = [button.callback_data for button in action_row]
    assert callbacks == ["g|n|1", "g|u|1", "g|c|1", "g|x|1"]


def test_long_title_is_truncated():
    long_title = "А" * 100
    _, markup = build_tasks_message([_task(1, title=long_title)])

    label = markup.inline_keyboard[0][0].text
    assert len(label) <= 50
    assert label.endswith("…")


def test_main_menu_has_expected_buttons_in_rows():
    markup = build_main_menu()

    rows = markup.keyboard
    assert [button.text for row in rows for button in row] == [
        MENU_TASKS,
        MENU_HABITS,
        MENU_GOALS,
        MENU_HELP,
    ]
    # Первая и последняя строка — по одной кнопке (во всю ширину),
    # средняя — две в один ряд (как на скрине-референсе пользователя).
    assert len(rows[0]) == 1
    assert len(rows[1]) == 2
    assert len(rows[2]) == 1


def test_main_menu_resizes_to_fit():
    markup = build_main_menu()

    assert markup.resize_keyboard is True
