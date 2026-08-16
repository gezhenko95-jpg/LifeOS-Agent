"""
Клавиатуры Telegram-бота: постоянное меню (ReplyKeyboardMarkup) и
inline-клавиатуры для списков задач/привычек/целей (InlineKeyboardMarkup).

Это два разных механизма Telegram, они не конфликтуют:
- ReplyKeyboardMarkup — меню снизу экрана, висит всегда, до явной замены;
  нажатие отправляет обычное текстовое сообщение (как будто напечатали).
- InlineKeyboardMarkup — кнопки под конкретным сообщением со списком,
  нажатие обрабатывается через callback_data (app/telegram/callbacks.py).

Оформление списков. Раньше весь список жил В КНОПКАХ: подпись кнопки
обрезалась по 45 символов, срок влезал в виде «— 20.08», а статуса не
было вообще. Теперь содержимое — в тексте сообщения (место не
ограничено, видно полное название, срок словами и цвет по срочности), а
кнопки стали короткими и пронумерованными: номер в кнопке совпадает с
номером в тексте.

Текст размечен HTML (parse_mode=HTML на стороне отправки). Всё, что
пришло от пользователя, обязательно проходит через _esc() — иначе
задача с названием «<b>» сломает разметку всего сообщения.

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

from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.goals.models import Goal
from app.habits.models import Habit
from app.tasks.formatting import (
    count_overdue,
    format_due_human,
    task_created_prefix,
    task_status_emoji,
)
from app.tasks.models import Task
from app.watchlist.models import MEDIA_TYPE_EMOJI, WatchlistItem

_MAX_ITEMS = 10
# Кнопок в ряду: больше пяти на узком экране схлопывается в нечитаемую кашу.
_BUTTONS_PER_ROW = 5
_DIVIDER = "━━━━━━━━━━━━━━━"

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


def _esc(text: str) -> str:
    """Экранировать пользовательский текст для parse_mode=HTML."""
    return escape(str(text), quote=False)


def _progress_bar(percent: int, width: int = 10) -> str:
    """▓▓▓▓▓▓░░░░ — прогресс виден боковым зрением, до чтения числа."""
    filled = round(max(0, min(100, percent)) / 100 * width)
    return "▓" * filled + "░" * (width - filled)


def _numbered_action_rows(
    items: list, callback_prefix: str, icon: str
) -> list[list[InlineKeyboardButton]]:
    """Ряды кнопок вида «✅ 1», «✅ 2»… Номер совпадает с номером в тексте
    сообщения, поэтому подпись не нужна — и не обрезается по длине, как
    раньше обрезались названия."""
    buttons = [
        InlineKeyboardButton(
            f"{icon} {index}", callback_data=f"{callback_prefix}|{item.id}"
        )
        for index, item in enumerate(items, start=1)
    ]
    return [
        buttons[i : i + _BUTTONS_PER_ROW]
        for i in range(0, len(buttons), _BUTTONS_PER_ROW)
    ]


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


def build_tasks_message(tasks: list[Task]) -> tuple[str, InlineKeyboardMarkup]:
    if not tasks:
        return (
            "📋 <b>Задачи</b>\n\nПусто — и это нормально. "
            "Напишите, что нужно сделать, и я запомню.",
            InlineKeyboardMarkup([]),
        )

    shown = tasks[:_MAX_ITEMS]
    lines = ["📋 <b>Задачи</b>", ""]
    for index, task in enumerate(shown, start=1):
        priority = "❗ " if task.priority == "high" else ""
        recurrence = " 🔁" if task.recurrence else ""
        lines.append(
            f"<b>{index}</b>  {task_status_emoji(task)} "
            f"{priority}{_esc(task.title)}{recurrence}"
        )
        if task.due_date:
            lines.append(f"      <i>{format_due_human(task.due_date)}</i>")
        lines.append("")

    lines.append(_DIVIDER)
    lines.append(_build_tasks_summary(tasks, len(shown)))

    rows = _numbered_action_rows(shown, "t|c", "✅")
    rows += _numbered_action_rows(shown, "t|d", "🗑")
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _build_tasks_summary(tasks: list[Task], shown_count: int) -> str:
    parts = [f"{len(tasks)} {_plural(len(tasks), 'активная', 'активные', 'активных')}"]
    overdue = count_overdue(tasks)
    if overdue:
        parts.append(
            f"⚠️ {overdue} "
            f"{_plural(overdue, 'просрочена', 'просрочены', 'просрочено')}"
        )
    hidden = len(tasks) - shown_count
    if hidden:
        # Раньше «лишние» задачи просто не показывались, и пользователь
        # считал, что их нет.
        parts.append(f"ещё {hidden} не поместилось")
    return " · ".join(parts)


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


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
    расхождения в стиле. Префикс "Добавил задачу: «…»" — общий хелпер
    (см. app/tasks/formatting.py::task_created_prefix), суффикс
    (срок/повтор) здесь однострочный, в отличие от engine.py."""
    suffix = f" на {format_due_human(task.due_date)}" if task.due_date else ""
    recurrence_suffix = " 🔁" if task.recurrence else ""
    text = f"{task_created_prefix(task)}{suffix}{recurrence_suffix}"
    markup = build_task_quick_actions_keyboard(task) or InlineKeyboardMarkup([])
    return text, markup


def build_habits_message(
    habits: list[Habit], streaks: dict[int, int]
) -> tuple[str, InlineKeyboardMarkup]:
    if not habits:
        return (
            "🔁 <b>Привычки</b>\n\nПока ни одной. "
            "Напишите «привычка чтение» — начнём считать серию.",
            InlineKeyboardMarkup([]),
        )

    shown = habits[:_MAX_ITEMS]
    lines = ["🔁 <b>Привычки</b>", ""]
    for index, habit in enumerate(shown, start=1):
        streak = streaks.get(habit.id, 0)
        lines.append(f"<b>{index}</b>  {_esc(habit.title)}")
        lines.append(f"      {_streak_line(streak)}")
        lines.append("")

    lines.append(_DIVIDER)
    best = max(streaks.values(), default=0)
    lines.append(
        f"{len(habits)} {_plural(len(habits), 'привычка', 'привычки', 'привычек')}"
        + (f" · рекорд серии 🔥 {best}" if best else "")
    )

    rows = _numbered_action_rows(shown, "h|d", "✅")
    rows += _numbered_action_rows(shown, "h|x", "🗑")
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _streak_line(streak: int) -> str:
    """Серия словами и полоской. Ноль — не «пусто», а приглашение начать:
    список привычек чаще всего открывают именно чтобы отметить."""
    if streak <= 0:
        return "<i>серии пока нет — самое время начать</i>"
    # Шкала до 30 дней: дальше полоска всё равно упёрлась бы в край, а
    # тридцати дней достаточно, чтобы привычка считалась закреплённой.
    bar = _progress_bar(round(min(streak, 30) / 30 * 100))
    return f"🔥 {streak} {_plural(streak, 'день', 'дня', 'дней')} подряд  {bar}"


def build_watchlist_message(
    items: list[WatchlistItem],
) -> tuple[str, InlineKeyboardMarkup]:
    if not items:
        return (
            "🎬 <b>Посмотреть и почитать</b>\n\nСписок пуст. "
            "Напишите «фильм Дюна» или «книга Дюна» — добавлю.",
            InlineKeyboardMarkup([]),
        )

    shown = items[:_MAX_ITEMS]
    lines = ["🎬 <b>Посмотреть и почитать</b>", ""]
    for index, item in enumerate(shown, start=1):
        emoji = MEDIA_TYPE_EMOJI.get(item.media_type, "🎯")
        lines.append(f"<b>{index}</b>  {emoji} {_esc(item.title)}")
    lines.append("")
    lines.append(_DIVIDER)
    lines.append(f"{len(items)} в списке")

    rows = _numbered_action_rows(shown, "w|d", "✅")
    rows += _numbered_action_rows(shown, "w|x", "🗑")
    rows.append([InlineKeyboardButton("🎲 Порекомендуй", callback_data="w|r|0")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_goals_message(goals: list[Goal]) -> tuple[str, InlineKeyboardMarkup]:
    if not goals:
        return (
            "🎯 <b>Цели</b>\n\nНи одной активной цели. "
            "Расскажите, к чему идёте — буду напоминать о сроках.",
            InlineKeyboardMarkup([]),
        )

    shown = goals[:_MAX_ITEMS]
    lines = ["🎯 <b>Цели</b>", ""]
    rows = []
    for index, goal in enumerate(shown, start=1):
        lines.append(f"<b>{index}</b>  {_esc(goal.title)}")
        lines.append(f"      {_progress_bar(goal.progress)} {goal.progress}%")
        if goal.target_date:
            lines.append(f"      <i>до {goal.target_date:%d.%m.%Y}</i>")
        lines.append("")
        # У целей действий четыре, номерами их не развести — оставляем
        # ряд на цель, но с номером, чтобы связь с текстом не терялась.
        rows.append(
            [
                InlineKeyboardButton(f"{index}", callback_data="g|noop"),
                InlineKeyboardButton("➖10%", callback_data=f"g|n|{goal.id}"),
                InlineKeyboardButton("➕10%", callback_data=f"g|u|{goal.id}"),
                InlineKeyboardButton("✅", callback_data=f"g|c|{goal.id}"),
                InlineKeyboardButton("🗑", callback_data=f"g|x|{goal.id}"),
            ]
        )

    lines.append(_DIVIDER)
    average = round(sum(g.progress for g in goals) / len(goals))
    lines.append(
        f"{len(goals)} {_plural(len(goals), 'цель', 'цели', 'целей')} "
        f"· средний прогресс {average}%"
    )
    return "\n".join(lines), InlineKeyboardMarkup(rows)
