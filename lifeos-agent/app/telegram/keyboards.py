"""
Клавиатуры Telegram-бота: постоянное меню (ReplyKeyboardMarkup) и
inline-клавиатуры для списков задач/привычек/целей (InlineKeyboardMarkup).

Это два разных механизма Telegram, они не конфликтуют:
- ReplyKeyboardMarkup — меню снизу экрана, висит всегда, до явной замены;
  нажатие отправляет обычное текстовое сообщение (как будто напечатали).
- InlineKeyboardMarkup — кнопки под конкретным сообщением со списком,
  нажатие обрабатывается через callback_data (app/telegram/callbacks.py).

Чистые функции — только презентация, никакого доступа к БД/сети.
callback_data — компактный формат "{домен}|{действие}|{id}":
  t|c|{id} / t|d|{id} — задача: выполнить / удалить
  t|p|{id} / t|w|{id} — задача: сделать важной / поставить дату на завтра
    (быстрые кнопки под подтверждением создания, см. handlers.py)
  h|d|{id} / h|x|{id} — привычка: отметить сегодня / удалить
  g|u|{id} / g|n|{id} / g|c|{id} / g|x|{id} — цель: +10% / -10% / завершить / удалить
  g|noop — строка-заголовок цели, не действие
  w|d|{id} / w|x|{id} — watchlist: отметить готовым / удалить
  w|r|0 — «Порекомендуй» (id не нужен, действует на весь список)
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.goals.models import Goal
from app.habits.models import Habit
from app.tasks.models import Task
from app.watchlist.models import WatchlistItem

_MAX_ITEMS = 10
_LABEL_LIMIT = 45

# Текст кнопок меню — по этому же тексту handlers.py распознаёт нажатие
# (см. _MENU_ACTIONS в app/telegram/handlers.py).
MENU_TASKS = "📋 Задачи"
MENU_HABITS = "🔁 Привычки"
MENU_GOALS = "🎯 Цели"
MENU_ADD_TASK = "➕ Задача"
MENU_JOURNAL = "📝 Дневник"
MENU_INSIGHTS = "📊 Инсайты"
MENU_WATCHLIST = "🎬 Посмотреть"
MENU_SITE = "🌐 Сайт"
MENU_HELP = "❓ Помощь"

_MEDIA_TYPE_EMOJI = {"movie": "🎬", "book": "📖"}


def build_open_site_keyboard(url: str) -> InlineKeyboardMarkup:
    """Кнопка «Открыть сайт» со ссылкой на /ui — ReplyKeyboardMarkup не
    умеет открывать URL, только InlineKeyboardButton(url=...) умеет
    (см. app/telegram/handlers.py::_send_site_link)."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("Открыть сайт", url=url)]])


def build_main_menu() -> ReplyKeyboardMarkup:
    """Постоянное меню снизу экрана — не привязано к сообщению."""
    keyboard = [
        [KeyboardButton(MENU_TASKS)],
        [KeyboardButton(MENU_HABITS), KeyboardButton(MENU_GOALS)],
        [KeyboardButton(MENU_ADD_TASK), KeyboardButton(MENU_JOURNAL)],
        [KeyboardButton(MENU_INSIGHTS), KeyboardButton(MENU_WATCHLIST)],
        [KeyboardButton(MENU_SITE), KeyboardButton(MENU_HELP)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _truncate(text: str, limit: int = _LABEL_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_tasks_message(tasks: list[Task]) -> tuple[str, InlineKeyboardMarkup]:
    if not tasks:
        return "Активных задач нет.", InlineKeyboardMarkup([])

    rows = []
    for task in tasks[:_MAX_ITEMS]:
        prefix = "❗ " if task.priority == "high" else ""
        suffix = f" — {task.due_date:%d.%m}" if task.due_date else ""
        label = _truncate(f"✅ {prefix}{task.title}{suffix}")
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"t|c|{task.id}"),
                InlineKeyboardButton("🗑", callback_data=f"t|d|{task.id}"),
            ]
        )
    return "Ваши задачи:", InlineKeyboardMarkup(rows)


def build_task_quick_actions_keyboard(task: Task) -> InlineKeyboardMarkup | None:
    """Кнопки под подтверждением создания задачи — только то, что ещё не
    задано (не предлагаем "Важно", если уже важная). None, если предлагать
    нечего (уже и приоритет high, и дата есть)."""
    buttons = []
    if task.priority != "high":
        buttons.append(InlineKeyboardButton("❗ Важно", callback_data=f"t|p|{task.id}"))
    if task.due_date is None:
        buttons.append(
            InlineKeyboardButton("📅 Завтра", callback_data=f"t|w|{task.id}")
        )
    if not buttons:
        return None
    return InlineKeyboardMarkup([buttons])


def build_task_confirmation_message(task: Task) -> tuple[str, InlineKeyboardMarkup]:
    """Текст+кнопки после изменения задачи через быструю кнопку (см.
    app/telegram/callbacks.py) — тот же формат, что и у ConversationEngine
    при создании (app/conversation/engine.py::_add_task), чтобы не было
    расхождения в стиле."""
    prefix = "❗ " if task.priority == "high" else ""
    suffix = f" на {task.due_date:%d.%m.%Y}" if task.due_date else ""
    recurrence_suffix = " 🔁" if task.recurrence else ""
    text = f"{prefix}Добавил задачу: «{task.title}»{suffix}{recurrence_suffix}"
    markup = build_task_quick_actions_keyboard(task) or InlineKeyboardMarkup([])
    return text, markup


def build_habits_message(
    habits: list[Habit], streaks: dict[int, int]
) -> tuple[str, InlineKeyboardMarkup]:
    if not habits:
        return "Активных привычек нет.", InlineKeyboardMarkup([])

    rows = []
    for habit in habits[:_MAX_ITEMS]:
        streak = streaks.get(habit.id, 0)
        suffix = f" 🔥{streak}" if streak > 0 else ""
        label = _truncate(f"✅ {habit.title}{suffix}")
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"h|d|{habit.id}"),
                InlineKeyboardButton("🗑", callback_data=f"h|x|{habit.id}"),
            ]
        )
    return "Ваши привычки:", InlineKeyboardMarkup(rows)


def build_watchlist_message(
    items: list[WatchlistItem],
) -> tuple[str, InlineKeyboardMarkup]:
    if not items:
        return "Смотреть/читать пока нечего.", InlineKeyboardMarkup([])

    rows = []
    for item in items[:_MAX_ITEMS]:
        emoji = _MEDIA_TYPE_EMOJI.get(item.media_type, "🎯")
        label = _truncate(f"✅ {emoji} {item.title}")
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"w|d|{item.id}"),
                InlineKeyboardButton("🗑", callback_data=f"w|x|{item.id}"),
            ]
        )
    rows.append([InlineKeyboardButton("🎲 Порекомендуй", callback_data="w|r|0")])
    return "Хочешь посмотреть/прочитать:", InlineKeyboardMarkup(rows)


def build_goals_message(goals: list[Goal]) -> tuple[str, InlineKeyboardMarkup]:
    if not goals:
        return "Активных целей нет.", InlineKeyboardMarkup([])

    rows = []
    for goal in goals[:_MAX_ITEMS]:
        title_label = _truncate(f"{goal.title} — {goal.progress}%")
        rows.append([InlineKeyboardButton(title_label, callback_data="g|noop")])
        rows.append(
            [
                InlineKeyboardButton("➖10%", callback_data=f"g|n|{goal.id}"),
                InlineKeyboardButton("➕10%", callback_data=f"g|u|{goal.id}"),
                InlineKeyboardButton("✅ Готово", callback_data=f"g|c|{goal.id}"),
                InlineKeyboardButton("🗑", callback_data=f"g|x|{goal.id}"),
            ]
        )
    return "Ваши цели:", InlineKeyboardMarkup(rows)
