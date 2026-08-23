"""
Обработка нажатий на inline-кнопки (см. app/telegram/keyboards.py).
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.core.config import get_settings
from app.core.container import (
    build_digest_service,
    build_finance_service,
    build_rewards_service,
)
from app.db.session import AsyncSessionLocal
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.habits.templates import get_template
from app.memory.models import MemoryType
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.proactive.repository import PendingPromptRepository
from app.tasks.models import Task
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
from app.telegram.handlers import JOURNAL_PROMPT
from app.telegram.keyboards import (
    build_digest_detail_message,
    build_digest_menu_message,
    build_finance_menu,
    build_finance_message,
    build_goals_menu,
    build_goals_message,
    build_habit_templates_message,
    build_habits_menu,
    build_habits_message,
    build_journal_entries_message,
    build_journal_entry_message,
    build_journal_menu,
    build_task_confirmation_message,
    build_tasks_menu,
    build_tasks_message,
    build_watchlist_menu,
    build_watchlist_message,
)
from app.telegram.pending_input import (
    DIGEST_CHANNEL,
    DIGEST_NEW,
    FINANCE_EXPENSE_ADD,
    FINANCE_INCOME_ADD,
    GOAL_ADD,
    HABIT_ADD,
    JOURNAL_SEARCH,
    TASK_ADD,
    WATCHLIST_ADD,
    PendingInput,
    set_pending,
)
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService

# 9:00 — тот же час по умолчанию, что и у date_parser.py для дат без
# явного времени (не импортируем оттуда приватную константу).
_DEFAULT_HOUR = 9


def _current_month_start() -> datetime:
    """Тот же расчёт периода, что и в app/scheduler/finance_report.py —
    экран «Список» и еженедельный отчёт не должны расходиться в
    определении «этого месяца»."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# Кнопки без id: действуют на раздел целиком, а не на сущность (см.
# app/telegram/keyboards.py, где перечислен весь формат callback_data).
_SECTION_DOMAINS = ("t", "h", "g", "j", "w", "d", "f")
_IDLESS_ACTIONS = {
    # Общие для всех разделов: экран раздела / список / добавить.
    *((domain, action) for domain in _SECTION_DOMAINS for action in ("m", "l", "n")),
    ("w", "r"),  # порекомендуй — действует на весь список
    ("j", "f"),  # поиск по теме
    ("h", "t"),  # каталог готовых привычек
    ("f", "i"),  # финансы: добавить ДОХОД — второй "add" без своего id
}

# Действия, у которых третья часть callback_data — НЕ число. Пока такое
# одно: slug готовой привычки (каталог живёт в коде, числовых id у него
# нет, см. app/habits/templates.py). Числовую проверку для них
# пропускаем, а сам разбор делает обработчик домена.
_NON_NUMERIC_ACTIONS = {("h", "a")}

# Что бот отвечает, когда ждёт ввод после кнопки. Одинаковый приём во
# всех разделах: сообщение превращается в приглашение, следующее
# сообщение пользователя ловит app/telegram/handlers.py.
_ASK_TASK = (
    "📋 <b>Что за задача?</b>\n\n"
    "Напишите как есть — «завтра в 19:00 позвонить маме» или просто «купить хлеб»."
)
_ASK_HABIT = (
    "🔁 <b>Какую привычку заводим?</b>\n\nОдно-два слова — «чтение», «зарядка»."
)
_ASK_GOAL = "🎯 <b>Какая цель?</b>\n\nНапишите коротко — «выучить испанский», «пробежать 10 км»."
_ASK_WATCHLIST = (
    "🎬 <b>Что добавить на полку?</b>\n\n"
    "Напишите название — «Дюна», или с типом: «фильм Дюна», «книга Дюна»."
)
_ASK_JOURNAL_SEARCH = (
    "🔍 <b>Что найти в дневнике?</b>\n\nНапишите слово или тему — например, «работа»."
)
_ASK_DIGEST_NEW = (
    "📰 <b>Как назовём дайджест?</b>\n\n"
    "Одно слово — «ESG». Можно сразу с частотой: «ESG daily» или «ESG weekly»."
)
_ASK_DIGEST_CHANNEL = (
    "➕ <b>Какой канал добавить?</b>\n\n"
    "Имя публичного канала — «durov», «@durov» или ссылка t.me/durov."
)
_ASK_FINANCE_EXPENSE = (
    "💸 <b>Сколько и на что?</b>\n\nНапишите сумму и, если хотите, категорию — "
    "«500 такси» или просто «500»."
)
_ASK_FINANCE_INCOME = "💰 <b>Сколько получили?</b>\n\nПросто сумма — «80000»."

logger = logging.getLogger(__name__)


async def _reward_line(session: AsyncSession, telegram_user_id: int) -> str:
    """Любое "сделал" действие по кнопке засчитывает сегодняшний визит в
    rewards — не только отдельный поход в /ui и клик "Забрать" (см.
    specs/016-engagement-hooks.md: единственное, что реально приживается
    в этом боте, не требует отдельного "зайти и нажать", а награда за
    остальное никак не показывалась). "" на повторном за день действии —
    coins_today не начисляется дважды, показывать нечего."""
    status = await build_rewards_service(session).claim_today(telegram_user_id)
    if not status.just_claimed:
        return ""
    return f"\n\n🪙 +{status.coins_today} · 🔥 {status.streak}"


def parse_callback(data: str) -> tuple[str, str, str] | None:
    """ "t|c|5" -> ("t", "c", "5"). Отдельная чистая функция для тестов.

    None на мусорном значении: раньше строка без "|" роняла распаковку
    (ValueError), а исключение уходило в лог, оставляя пользователя без
    ответа (см. AUDIT.md, B-3).
    """
    domain, _, rest = data.partition("|")
    action, _, item_id = rest.partition("|")
    if not domain or not action:
        return None
    return domain, action, item_id


def _parse_item_id(item_id: str) -> int | None:
    """None вместо ValueError на нечисловом id (см. parse_callback)."""
    try:
        return int(item_id)
    except ValueError:
        return None


async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    # У CallbackQueryHandler нет параметра filters (в отличие от
    # Message/CommandHandler, см. app/telegram/bot.py), поэтому владельца
    # проверяем здесь. Без проверки посторонний мог перебором id
    # выполнять и удалять чужие задачи/привычки/цели — id приходит прямо
    # из callback_data (см. AUDIT.md, C-4/B-2).
    owner_id = get_settings().owner_telegram_user_id
    if owner_id and update.effective_user.id != owner_id:
        await query.answer("Этот бот личный.", show_alert=True)
        return

    await query.answer()

    parsed = parse_callback(query.data)
    if parsed is None:
        return
    domain, action, item_id = parsed
    if domain == "g" and action == "noop":
        return

    # Часть кнопок действует не на конкретную сущность, а на раздел
    # целиком («Порекомендуй», «Записи», «◀️ Назад») — им id не нужен и не
    # передаётся. Всем остальным нужен корректный числовой id.
    skips_numeric_id = (domain, action) in _IDLESS_ACTIONS or (
        domain,
        action,
    ) in _NON_NUMERIC_ACTIONS
    if not skips_numeric_id and _parse_item_id(item_id) is None:
        return

    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        if domain == "t":
            text, markup = await _handle_task_action(
                session, action, item_id, telegram_user_id, context
            )
        elif domain == "h":
            text, markup = await _handle_habit_action(
                session, action, item_id, telegram_user_id, context
            )
        elif domain == "g":
            text, markup = await _handle_goal_action(
                session, action, item_id, telegram_user_id, context
            )
        elif domain == "w":
            text, markup = await _handle_watchlist_action(
                session, action, item_id, telegram_user_id, context
            )
        elif domain == "j":
            text, markup = await _handle_journal_action(
                session, action, item_id, telegram_user_id, context
            )
        elif domain == "d":
            text, markup = await _handle_digest_action(
                session, action, item_id, telegram_user_id, context, query
            )
        elif domain == "f":
            text, markup = await _handle_finance_action(
                session, action, item_id, telegram_user_id, context
            )
        else:
            return

    try:
        await query.edit_message_text(
            text, reply_markup=markup, parse_mode=ParseMode.HTML
        )
    except BadRequest as exc:
        # "Message is not modified" — обычный двойной тап по кнопке, когда
        # результат не изменился (например, повторное «готово» на уже
        # отмеченной привычке). Это не ошибка, ронять хендлер незачем
        # (см. AUDIT.md, B-4).
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Сообщение не изменилось, перерисовка пропущена")


async def _handle_task_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    service = TaskService(TaskRepository(session))

    if action == "m":
        return build_tasks_menu()
    if action == "n":
        set_pending(context.user_data, PendingInput(TASK_ADD))
        return _ASK_TASK, InlineKeyboardMarkup([])

    if action == "p":
        task = await service.update_task(
            telegram_user_id, int(item_id), priority="high"
        )
        return _quick_action_result(task)
    if action == "w":
        tomorrow = datetime.combine(
            date.today() + timedelta(days=1), time(hour=_DEFAULT_HOUR)
        ).astimezone()
        task = await service.update_task(
            telegram_user_id, int(item_id), due_date=tomorrow
        )
        return _quick_action_result(task)

    reward = ""
    if action == "c":
        completed = await service.update_task(
            telegram_user_id, int(item_id), status="completed"
        )
        if completed is not None:
            reward = await _reward_line(session, telegram_user_id)
    elif action == "d":
        await service.delete_task(telegram_user_id, int(item_id))
    tasks = await service.list_active_tasks(telegram_user_id)
    text, markup = build_tasks_message(tasks)
    return text + reward, markup


def _quick_action_result(task: Task | None) -> tuple[str, InlineKeyboardMarkup]:
    if task is None:
        # Задачу успели удалить/завершить, пока кнопка ещё была на экране.
        return "Задача больше не активна.", InlineKeyboardMarkup([])
    return build_task_confirmation_message(task)


async def _handle_habit_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    service = HabitService(HabitRepository(session))
    if action == "m":
        return build_habits_menu()
    if action == "n":
        set_pending(context.user_data, PendingInput(HABIT_ADD))
        return _ASK_HABIT, InlineKeyboardMarkup([])
    if action == "t":
        return build_habit_templates_message()
    reward = ""
    if action == "a":
        # Здесь в item_id приходит slug шаблона, а не число (см.
        # _NON_NUMERIC_ACTIONS): каталог живёт в коде, id у него нет.
        template = get_template(item_id)
        if template is None:
            return "Такой готовой привычки больше нет.", InlineKeyboardMarkup([])
        await service.create_from_template(telegram_user_id, template)
    if action == "d":
        done = await service.mark_done_by_id(telegram_user_id, int(item_id))
        if done is not None:
            reward = await _reward_line(session, telegram_user_id)
    elif action == "x":
        await service.delete_habit(telegram_user_id, int(item_id))
    habits = await service.list_active_habits(telegram_user_id)
    streaks = await service.get_streaks_bulk(telegram_user_id, [h.id for h in habits])
    text, markup = build_habits_message(habits, streaks)
    return text + reward, markup


async def _handle_goal_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    service = GoalService(GoalRepository(session))
    if action == "m":
        return build_goals_menu()
    if action == "n":
        set_pending(context.user_data, PendingInput(GOAL_ADD))
        return _ASK_GOAL, InlineKeyboardMarkup([])
    reward = ""
    if action in ("u", "p"):
        goals = await service.list_active_goals(telegram_user_id)
        goal = next((g for g in goals if g.id == int(item_id)), None)
        if goal is not None:
            delta = 10 if action == "u" else -10
            new_progress = max(0, min(100, goal.progress + delta))
            await service.update_progress(telegram_user_id, goal.id, new_progress)
            # Только рост прогресса — награда за движение вперёд, не за
            # откат назад (action == "p" его не получает).
            if action == "u":
                reward = await _reward_line(session, telegram_user_id)
    elif action == "c":
        completed = await service.complete_goal(telegram_user_id, int(item_id))
        if completed is not None:
            reward = await _reward_line(session, telegram_user_id)
    elif action == "x":
        await service.delete_goal(telegram_user_id, int(item_id))
    goals = await service.list_active_goals(telegram_user_id)
    text, markup = build_goals_message(goals)
    return text + reward, markup


async def _handle_watchlist_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    service = WatchlistService(WatchlistRepository(session))
    if action == "m":
        return build_watchlist_menu()
    if action == "n":
        set_pending(context.user_data, PendingInput(WATCHLIST_ADD))
        return _ASK_WATCHLIST, InlineKeyboardMarkup([])
    reward = ""
    if action == "d":
        done = await service.mark_done(telegram_user_id, int(item_id))
        if done is not None:
            reward = await _reward_line(session, telegram_user_id)
    elif action == "x":
        await service.delete_item(telegram_user_id, int(item_id))
    elif action == "r":
        recommendation = await service.pick_recommendation(
            telegram_user_id, get_ai_client()
        )
        text = recommendation or "Смотреть/читать пока нечего."
        return text, InlineKeyboardMarkup([])

    items = await service.list_active_items(telegram_user_id)
    text, markup = build_watchlist_message(items)
    return text + reward, markup


async def _handle_finance_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    """У финансов два "add" (см. keyboards.py::build_finance_menu) —
    "n" (трата, как везде) и "i" (доход). "x" — удалить транзакцию, без
    награды (удаление нигде в проекте не награждается, см.
    specs/016-engagement-hooks.md). Любое другое действие ("l" и
    default) — показать список за текущий месяц с итогами."""
    service = build_finance_service(session)

    if action == "m":
        return build_finance_menu()
    if action == "n":
        set_pending(context.user_data, PendingInput(FINANCE_EXPENSE_ADD))
        return _ASK_FINANCE_EXPENSE, InlineKeyboardMarkup([])
    if action == "i":
        set_pending(context.user_data, PendingInput(FINANCE_INCOME_ADD))
        return _ASK_FINANCE_INCOME, InlineKeyboardMarkup([])
    if action == "x":
        await service.delete_transaction(telegram_user_id, int(item_id))

    transactions = await service.list_recent_transactions(telegram_user_id)
    summary = await service.build_period_summary(
        telegram_user_id, _current_month_start()
    )
    return build_finance_message(transactions, summary)


async def _handle_journal_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    """Дневник как раздел: список записей → одна запись целиком, поиск по
    теме и новая запись. Записи — это MemoryEntry типа journal (отдельной
    таблицы у дневника нет, см. specs/001-memory.md)."""
    if action == "m":
        return build_journal_menu()
    if action == "f":
        set_pending(context.user_data, PendingInput(JOURNAL_SEARCH))
        return _ASK_JOURNAL_SEARCH, InlineKeyboardMarkup([])
    if action == "n":
        # Тот же механизм, что у кнопки «📝 Дневник» до появления экранов
        # раздела: открытый journal-pending, следующее сообщение движок
        # сохранит как запись целиком (см. ConversationEngine.
        # _try_capture_journal). Это НЕ pending_input: дневниковая запись
        # переживает рестарт и осмысленна часами, а не секунды.
        await PendingPromptRepository(session).upsert(
            telegram_user_id, "journal", JOURNAL_PROMPT
        )
        return JOURNAL_PROMPT, InlineKeyboardMarkup([])

    service = MemoryService(MemoryRepository(session))
    if action == "o":
        entry = await service.get_entry(telegram_user_id, int(item_id))
        if entry is None:
            return "Этой записи больше нет.", InlineKeyboardMarkup([])
        return build_journal_entry_message(entry)

    entries = await service.list_entries(telegram_user_id, type=MemoryType.JOURNAL)
    return build_journal_entries_message(entries)


async def _handle_digest_action(
    session: AsyncSession,
    action: str,
    item_id: str,
    telegram_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    query: CallbackQuery,
) -> tuple[str, InlineKeyboardMarkup]:
    """Дайджесты как раздел: список тем → одна тема (её каналы) →
    «что нового» прямо сейчас. Всё то же, что умеют команды /digest_*,
    но без запоминания синтаксиса."""
    service = build_digest_service(session)

    if action == "n":
        set_pending(context.user_data, PendingInput(DIGEST_NEW))
        return _ASK_DIGEST_NEW, InlineKeyboardMarkup([])

    if action == "m":
        return build_digest_menu_message(await service.list_digests(telegram_user_id))

    if action == "x":
        digest = await service.remove_channel_by_id(telegram_user_id, int(item_id))
        if digest is None:
            return "Этого канала больше нет.", InlineKeyboardMarkup([])
        return build_digest_detail_message(
            digest, await service.list_channels(digest.id)
        )

    digest = await service.get_digest(telegram_user_id, int(item_id))
    if digest is None:
        return "Этого дайджеста больше нет.", InlineKeyboardMarkup([])

    if action == "a":
        set_pending(context.user_data, PendingInput(DIGEST_CHANNEL, digest.id))
        return _ASK_DIGEST_CHANNEL, InlineKeyboardMarkup([])

    if action == "f":
        # Кнопка приходит от send_digests_job (app/telegram/jobs.py) —
        # висит под УЖЕ отправленным сообщением дайджеста. Текст поста
        # не хранится нигде отдельно (build_digest_text сплющивает посты
        # в одну строку и не сохраняет их), поэтому источник — само
        # сообщение, на котором висит кнопка, а не повторный запрос к
        # DigestService (см. specs/016-engagement-hooks.md, "Дайджест:
        # ⭐ Сохранить" — там же объяснение, почему не кнопка на пост).
        saved_text = query.message.text if query.message is not None else None
        if not saved_text:
            return "Нечего сохранять — сообщение уже пустое.", InlineKeyboardMarkup([])
        memory_service = MemoryService(MemoryRepository(session))
        await memory_service.save(
            telegram_user_id, MemoryType.JOURNAL, saved_text, source="digest_save"
        )
        reward = await _reward_line(session, telegram_user_id)
        # Пустая клавиатура снимает кнопку — повторный тап на тот же
        # дайджест физически невозможен (не нужен отдельный флаг в БД).
        return f"⭐ «{digest.name}» сохранён в дневник.{reward}", InlineKeyboardMarkup(
            []
        )

    if action == "r":
        # Чтение каналов по сети + AI-саммари — это секунды, а сообщение
        # всё это время выглядит нетронутым. «Печатает…» здесь — тот же
        # приём, что и в handlers.py на долгих ответах.
        await query.get_bot().send_chat_action(
            chat_id=telegram_user_id, action=ChatAction.TYPING
        )
        text = await service.build_digest_text(
            telegram_user_id, digest.name, ai_client=get_ai_client()
        )
        channels = await service.list_channels(digest.id)
        if text is None:
            detail, markup = build_digest_detail_message(digest, channels)
            return f"Новых постов пока нет.\n\n{detail}", markup
        # Саммари приходит от модели как обычный текст: HTML-разметки в
        # нём нет, а угловые скобки из поста сломали бы parse_mode=HTML.
        return escape(text, quote=False), InlineKeyboardMarkup([])

    # action == "s" (и любое неизвестное действие домена) — открыть тему.
    return build_digest_detail_message(digest, await service.list_channels(digest.id))
