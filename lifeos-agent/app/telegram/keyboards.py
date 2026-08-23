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

ОДНО ПРАВИЛО НА ВСЕ РАЗДЕЛЫ. Кнопка постоянного меню, за которой стоит
домен (задачи, привычки, цели, дневник, полка, дайджесты), всегда
открывает ЭКРАН РАЗДЕЛА — сообщение с одинаковым каркасом (см.
_section_screen): заголовок, строка-подсказка, ряд действий «открыть
список» + «добавить». Само действие делают уже inline-кнопки. Раньше
правило приходилось помнить для каждой кнопки отдельно: «📋 Задачи»
открывали список сразу, «➕ Задача» была отдельной кнопкой меню, «🎬
Посмотреть» — тоже сразу список, а добавление на полку жило только во
фразе «фильм Дюна». Кнопки-утилиты без своего домена («📊 Инсайты»,
«🌐 Сайт», «❓ Помощь») остаются прямым действием — экран из одного
пункта был бы лишним щелчком.

Из любого списка «◀️ Назад» возвращает на экран своего раздела.

Чистые функции — только презентация, никакого доступа к БД/сети.
callback_data — компактный формат "{домен}|{действие}|{id}".

Домены: t — задачи, h — привычки, g — цели, j — дневник, w — полка,
d — дайджесты, f — финансы, c — контакты (личный CRM), m — настроение.
Действия одинаковы во всех доменах:
  {домен}|m — экран раздела
  {домен}|l — открыть список
  {домен}|n — добавить (бот ждёт следующее сообщение, см. pending_input.py)

Домен-специфичное:
  t|c|{id} / t|d|{id} — задача: выполнить / удалить
  t|p|{id} / t|w|{id} — задача: сделать важной / поставить дату на завтра
    (быстрые кнопки под подтверждением создания, см. handlers.py)
  h|d|{id} / h|x|{id} — привычка: отметить сегодня / удалить
  g|u|{id} / g|p|{id} / g|c|{id} / g|x|{id} — цель: +10% / -10% /
    завершить / удалить
  g|noop — строка-заголовок цели, не действие
  w|d|{id} / w|x|{id} — полка: отметить готовым / удалить
  w|r|0 — «Порекомендуй» (действует на весь список)
  j|f — поиск по теме, j|o|{id} — открыть запись целиком
  d|s|{id} / d|r|{id} / d|a|{id} — дайджест: открыть / прислать новое /
    добавить канал
  d|x|{channel_id} — убрать канал (id КАНАЛА, не дайджеста)
  f|i — финансы: добавить ДОХОД (два вида "добавить" — f|n, как везде,
    для траты, и f|i для дохода); f|x|{id} — удалить транзакцию
  c|d|{id} / c|x|{id} — контакт: отметить «написал(а)» / удалить
  m|s|{score} — настроение: записать оценку 1-5 (используется и под
    вечерним дневниковым вопросом, и в разделе «Настроение»); m|x|{id} —
    удалить запись

Действия без id ("w|m", "j|l", …) — намеренно двухчастные: в
callback_data Telegram даёт 64 БАЙТА, и имя дайджеста туда класть нельзя
(кириллица + до 50 символов), поэтому везде, где нужна сущность, ездит
её числовой id (см. app/telegram/callbacks.py::parse_callback).
"""

from datetime import datetime, timezone
from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.crm.models import Contact
from app.digest.models import Digest, DigestChannel
from app.finance.models import CATEGORIES, EXPENSE, Transaction
from app.finance.service import FinanceSummary
from app.goals.models import Goal
from app.habits.models import Habit
from app.habits.templates import HABIT_TEMPLATES
from app.memory.models import MemoryEntry
from app.mood.models import MAX_SCORE, MIN_SCORE, SCORE_EMOJI, MoodEntry
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
MENU_JOURNAL = "📝 Дневник"
MENU_INSIGHTS = "📊 Инсайты"
MENU_WATCHLIST = "🎬 Посмотреть"
MENU_DIGEST = "📰 Дайджест"
MENU_FINANCE = "💰 Финансы"
MENU_CONTACTS = "📇 Люди"
MENU_MOOD = "😊 Настроение"
MENU_SITE = "🌐 Сайт"
MENU_HELP = "❓ Помощь"

# Столько записей дневника показываем на экране «📖 Записи» — дальше
# сообщение и ряды кнопок перестают читаться (тот же порядок, что
# _MAX_ITEMS у списков).
_MAX_JOURNAL_ENTRIES = 8
# Длина превью записи в списке: полный текст открывается кнопкой.
_JOURNAL_PREVIEW_CHARS = 60

_BACK_TO_JOURNAL = InlineKeyboardButton("◀️ Назад", callback_data="j|m")
_BACK_TO_DIGESTS = InlineKeyboardButton("◀️ Назад", callback_data="d|m")


def _back_to_section(domain: str) -> list[InlineKeyboardButton]:
    """Ряд «◀️ Назад» на экран своего раздела. Один и тот же приём во всех
    доменах: из списка всегда можно вернуться туда, откуда пришёл, не
    трогая постоянное меню."""
    return [InlineKeyboardButton("◀️ Назад", callback_data=f"{domain}|m")]


def _section_screen(
    title: str, hint: str, rows: list[list[InlineKeyboardButton]]
) -> tuple[str, InlineKeyboardMarkup]:
    """Единый каркас экрана раздела: заголовок, одна строка-подсказка,
    ряды кнопок-действий.

    Все шесть разделов (задачи, привычки, цели, дневник, полка,
    дайджесты) строятся через него — раньше каждая кнопка меню вела себя
    по-своему (часть открывала список сразу, часть — экран), и правило
    «что будет, если нажать» приходилось помнить для каждой отдельно.
    """
    return f"{title}\n\n{hint}", InlineKeyboardMarkup(rows)


def _open_and_add(domain: str, open_label: str, add_label: str = "➕ Добавить"):
    """Скелет действий раздела: «открыть список» + «добавить». Порядок и
    подписи одинаковы везде — различается только эмодзи домена."""
    return [
        InlineKeyboardButton(open_label, callback_data=f"{domain}|l"),
        InlineKeyboardButton(add_label, callback_data=f"{domain}|n"),
    ]


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
        [KeyboardButton(MENU_JOURNAL), KeyboardButton(MENU_WATCHLIST)],
        [KeyboardButton(MENU_DIGEST), KeyboardButton(MENU_FINANCE)],
        [KeyboardButton(MENU_CONTACTS), KeyboardButton(MENU_MOOD)],
        [KeyboardButton(MENU_INSIGHTS), KeyboardButton(MENU_SITE)],
        [KeyboardButton(MENU_HELP)],
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
    rows.append(_back_to_section("t"))
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
    rows.append(_back_to_section("h"))
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
    rows.append(
        [
            InlineKeyboardButton("🎲 Порекомендуй", callback_data="w|r|0"),
            InlineKeyboardButton("➕ Добавить", callback_data="w|n"),
        ]
    )
    rows.append(_back_to_section("w"))
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
                # «g|n» во всех доменах означает «добавить», поэтому
                # «-10%» переехал на «g|p» (progress down).
                InlineKeyboardButton("➖10%", callback_data=f"g|p|{goal.id}"),
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
    rows.append(_back_to_section("g"))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _money(amount: int) -> str:
    """1234567 -> "1 234 567" — разряды пробелом, как в build_finance_report
    (app/scheduler/finance_report.py) — тот же вид числа в двух местах."""
    return f"{amount:,}".replace(",", " ")


def build_finance_message(
    transactions: list[Transaction], summary: FinanceSummary
) -> tuple[str, InlineKeyboardMarkup]:
    """У финансов, в отличие от остальных доменов, ДВЕ кнопки "добавить"
    (трата/доход, см. app/telegram/pending_input.py) — своя строка кнопок
    внизу вместо общего _open_and_add."""
    lines = ["💰 <b>Финансы</b>", ""]
    lines.append(f"Доход: {_money(summary.income_total)} ₽")
    lines.append(f"Обязательные платежи: {_money(summary.mandatory_total)} ₽")
    lines.append(f"Свободно: {_money(summary.free_money)} ₽")

    if summary.categories:
        lines.append("")
        for category in summary.categories:
            prefix = "⚠️ " if category.over_budget else ""
            lines.append(
                f"{prefix}{_esc(category.label)}: {_money(category.spent)} / "
                f"{_money(category.norm)} ₽ нормы"
            )

    add_row = [
        InlineKeyboardButton("➕ Трата", callback_data="f|n"),
        InlineKeyboardButton("➕ Доход", callback_data="f|i"),
    ]

    if not transactions:
        lines.append("")
        lines.append(_DIVIDER)
        lines.append("Записей пока нет. Напишите «потратил 500 на такси».")
        return "\n".join(lines), InlineKeyboardMarkup([add_row, _back_to_section("f")])

    shown = transactions[:_MAX_ITEMS]
    lines.append("")
    lines.append(_DIVIDER)
    lines.append("Последние:")
    for index, transaction in enumerate(shown, start=1):
        if transaction.kind == EXPENSE:
            label = CATEGORIES.get(
                transaction.category or "", transaction.category or ""
            )
            lines.append(
                f"<b>{index}</b>  💸 {_money(transaction.amount)} ₽ — {_esc(label)}"
            )
        else:
            lines.append(f"<b>{index}</b>  💰 {_money(transaction.amount)} ₽ — доход")

    rows = _numbered_action_rows(shown, "f|x", "🗑")
    rows.append(add_row)
    rows.append(_back_to_section("f"))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip


def build_contacts_message(
    contacts: list[Contact],
) -> tuple[str, InlineKeyboardMarkup]:
    """Давние контакты сверху (порядок уже задан репозиторием, см.
    ContactRepository.list_by_user) — список читается как "с кем
    написать в первую очередь"."""
    if not contacts:
        return (
            "📇 <b>Люди</b>\n\nПока никого. Добавьте того, кому иногда "
            "стоит написать первым.",
            InlineKeyboardMarkup([]),
        )

    now = datetime.now(timezone.utc)
    shown = contacts[:_MAX_ITEMS]
    lines = ["📇 <b>Люди</b>", ""]
    for index, contact in enumerate(shown, start=1):
        last_contact_at = contact.last_contact_at
        if last_contact_at.tzinfo is None:
            last_contact_at = last_contact_at.replace(tzinfo=timezone.utc)
        days_since = (now - last_contact_at).days
        overdue = "⚠️ " if days_since >= 30 else ""
        since_line = (
            "сегодня"
            if days_since <= 0
            else (f"{days_since} {_plural(days_since, 'день', 'дня', 'дней')} назад")
        )
        lines.append(f"<b>{index}</b>  {overdue}{_esc(contact.name)}")
        detail = f"      Писал(а): {since_line}"
        if contact.birthday_month and contact.birthday_day:
            detail += (
                f" · 🎂 {contact.birthday_day} "
                f"{_MONTHS_GENITIVE[contact.birthday_month - 1]}"
            )
        lines.append(detail)
        lines.append("")

    lines.append(_DIVIDER)
    lines.append(
        f"{len(contacts)} {_plural(len(contacts), 'контакт', 'контакта', 'контактов')}"
    )

    rows = _numbered_action_rows(shown, "c|d", "👋")
    rows += _numbered_action_rows(shown, "c|x", "🗑")
    rows.append(_back_to_section("c"))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_mood_prompt_keyboard() -> InlineKeyboardMarkup:
    """5 кнопок-эмодзи под вечерним дневниковым вопросом
    (specs/019-mood-tracker.md) — та же клавиатура переиспользуется в
    build_mood_menu ниже."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(SCORE_EMOJI[score], callback_data=f"m|s|{score}")
                for score in range(MIN_SCORE, MAX_SCORE + 1)
            ]
        ]
    )


def build_mood_menu() -> tuple[str, InlineKeyboardMarkup]:
    """В отличие от остальных разделов — без «➕ Добавить»: сама оценка
    настроения и есть единственное действие, отдельная кнопка-приглашение
    была бы лишним щелчком (тот же довод, что у кнопок-утилит без
    домена)."""
    rows = list(build_mood_prompt_keyboard().inline_keyboard)
    rows.append([InlineKeyboardButton("📋 История", callback_data="m|l")])
    return _section_screen("😊 <b>Настроение</b>", "Как сейчас?", rows)


def build_mood_message(entries: list[MoodEntry]) -> tuple[str, InlineKeyboardMarkup]:
    if not entries:
        return (
            "😊 <b>Настроение</b>\n\nЗаписей пока нет.",
            InlineKeyboardMarkup([_back_to_section("m")]),
        )

    shown = entries[:_MAX_ITEMS]
    lines = ["😊 <b>Настроение</b>", ""]
    for index, entry in enumerate(shown, start=1):
        when = entry.logged_at.strftime("%d.%m %H:%M")
        lines.append(
            f"<b>{index}</b>  {SCORE_EMOJI.get(entry.score, '')} "
            f"{entry.score}/5 — {when}"
        )

    lines.append(_DIVIDER)
    lines.append(
        f"{len(entries)} {_plural(len(entries), 'запись', 'записи', 'записей')}"
    )

    rows = _numbered_action_rows(shown, "m|x", "🗑")
    rows.append(_back_to_section("m"))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# --- Экраны разделов (второй уровень меню) --------------------------------


def build_tasks_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "📋 <b>Задачи</b>",
        "Посмотреть, что висит, или добавить новую?",
        [_open_and_add("t", "📋 Список")],
    )


def build_habits_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "🔁 <b>Привычки</b>",
        "Отметить сегодняшние, завести свою или взять готовую?",
        [
            _open_and_add("h", "🔁 Список"),
            [InlineKeyboardButton("✨ Готовые привычки", callback_data="h|t")],
        ],
    )


def build_habit_templates_message() -> tuple[str, InlineKeyboardMarkup]:
    """Готовые привычки из каталога (см. app/habits/templates.py) — по
    кнопке на штуку, с описанием в тексте. Пустой раздел «Привычки» —
    главная причина, по которой их не заводят: шаблон снимает выбор
    «что вообще считать привычкой»."""
    lines = ["✨ <b>Готовые привычки</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for template in HABIT_TEMPLATES:
        when = (
            f" · напомню в {template.reminder_time:%H:%M}"
            if template.reminder_time
            else ""
        )
        lines.append(
            f"{template.emoji} <b>{_esc(template.title)}</b>{when}\n"
            f"      <i>{_esc(template.description)}</i>"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    f"{template.emoji} {template.title}",
                    callback_data=f"h|a|{template.slug}",
                )
            ]
        )

    rows.append(_back_to_section("h"))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_goals_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "🎯 <b>Цели</b>",
        "Посмотреть прогресс или поставить новую цель?",
        [_open_and_add("g", "🎯 Список")],
    )


def build_finance_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "💰 <b>Финансы</b>",
        "Посмотреть траты за месяц или добавить новую запись?",
        [
            [
                InlineKeyboardButton("📋 Список", callback_data="f|l"),
                InlineKeyboardButton("➕ Трата", callback_data="f|n"),
                InlineKeyboardButton("➕ Доход", callback_data="f|i"),
            ]
        ],
    )


def build_contacts_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "📇 <b>Люди</b>",
        "Кому давно не писал(а), или новый человек?",
        [_open_and_add("c", "📋 Список")],
    )


def build_watchlist_menu() -> tuple[str, InlineKeyboardMarkup]:
    return _section_screen(
        "🎬 <b>Полка</b>",
        "Что отложено на посмотреть-почитать — или добавить новое?",
        [_open_and_add("w", "📚 Список")],
    )


def build_journal_menu() -> tuple[str, InlineKeyboardMarkup]:
    """У дневника к общему скелету добавлен «🔍 По теме»: записей
    со временем становится много, и листать их подряд бесполезно."""
    return _section_screen(
        "📝 <b>Дневник</b>",
        "Почитать записи или записать что-то новое?",
        [
            _open_and_add("j", "📖 Записи", "✍️ Новая запись"),
            [InlineKeyboardButton("🔍 По теме", callback_data="j|f")],
        ],
    )


def build_journal_entries_message(
    entries: list[MemoryEntry], header: str = "📖 <b>Записи дневника</b>"
) -> tuple[str, InlineKeyboardMarkup]:
    """Список записей: дата + начало текста, кнопка с номером открывает
    запись целиком (текст записи может быть длинным — в список он не
    влезает, а обрезка без возможности раскрыть бесполезна)."""
    if not entries:
        return (
            f"{header}\n\nЗаписей пока нет. "
            "Нажмите «✍️ Новая запись» — и пишите как есть.",
            InlineKeyboardMarkup([[_BACK_TO_JOURNAL]]),
        )

    shown = entries[:_MAX_JOURNAL_ENTRIES]
    lines = [header, ""]
    for index, entry in enumerate(shown, start=1):
        lines.append(
            f"<b>{index}</b>  <i>{entry.created_at:%d.%m}</i>  "
            f"{_esc(_preview(entry.content))}"
        )

    lines.append("")
    lines.append(_DIVIDER)
    hidden = len(entries) - len(shown)
    summary = f"{len(entries)} {_plural(len(entries), 'запись', 'записи', 'записей')}"
    if hidden:
        summary += f" · показаны последние {len(shown)}"
    lines.append(summary)

    rows = _numbered_action_rows(shown, "j|o", "📄")
    rows.append([_BACK_TO_JOURNAL])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_journal_entry_message(entry: MemoryEntry) -> tuple[str, InlineKeyboardMarkup]:
    """Одна запись целиком — дата словами в шапке, дальше текст как есть."""
    text = f"📝 <b>{entry.created_at:%d.%m.%Y}</b>\n\n{_esc(entry.content)}"
    rows = [
        [
            InlineKeyboardButton("◀️ К записям", callback_data="j|l"),
            _BACK_TO_JOURNAL,
        ]
    ]
    return text, InlineKeyboardMarkup(rows)


def _preview(content: str) -> str:
    single_line = " ".join(content.split())
    if len(single_line) <= _JOURNAL_PREVIEW_CHARS:
        return single_line
    return single_line[:_JOURNAL_PREVIEW_CHARS].rstrip() + "…"


def build_digest_menu_message(
    digests: list[Digest],
) -> tuple[str, InlineKeyboardMarkup]:
    """📰 Дайджест → выбрать существующий или создать новый. Каждый
    дайджест — своя кнопка (их единицы, не десятки), поэтому здесь можно
    позволить себе имя прямо в подписи, а не номер."""
    if not digests:
        return (
            "📰 <b>Дайджесты каналов</b>\n\nНи одного пока нет.\n"
            "Дайджест — это тема (например, ESG) и несколько публичных "
            "Telegram-каналов: я слежу за новыми постами и присылаю саммари.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("➕ Создать дайджест", callback_data="d|n")]]
            ),
        )

    lines = ["📰 <b>Дайджесты каналов</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for digest in digests:
        schedule = schedule_label(digest.auto_frequency)
        lines.append(f"📰 <b>{_esc(digest.name)}</b> — <i>{schedule}</i>")
        rows.append(
            [
                InlineKeyboardButton(
                    f"📰 {digest.name}", callback_data=f"d|s|{digest.id}"
                )
            ]
        )

    rows.append([InlineKeyboardButton("➕ Новый дайджест", callback_data="d|n")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def build_digest_detail_message(
    digest: Digest, channels: list[DigestChannel]
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран одного дайджеста: какие каналы внутри и что с ним можно
    сделать. Удаление канала — кнопка с номером под своим каналом в
    тексте, тем же приёмом, что у задач/привычек."""
    lines = [f"📰 <b>{_esc(digest.name)}</b>", ""]
    lines.append(f"Расписание: <i>{schedule_label(digest.auto_frequency)}</i>")
    lines.append("")

    if channels:
        lines.append("Каналы:")
        for index, channel in enumerate(channels, start=1):
            lines.append(f"<b>{index}</b>  @{_esc(channel.channel_username)}")
    else:
        lines.append("Каналов пока нет — добавьте первый.")

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📬 Что нового", callback_data=f"d|r|{digest.id}"),
            InlineKeyboardButton("➕ Канал", callback_data=f"d|a|{digest.id}"),
        ]
    ]
    if channels:
        rows += _numbered_action_rows(channels, "d|x", "🗑")
    rows.append([_BACK_TO_DIGESTS])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def schedule_label(auto_frequency: str | None) -> str:
    """Одна формулировка расписания на все экраны — тот же текст, что и в
    ответах команд /digest_list и /digest_new (см. handlers.py)."""
    if auto_frequency == "daily":
        return "каждый день"
    if auto_frequency == "weekly":
        return "по воскресеньям"
    return "только по запросу"
