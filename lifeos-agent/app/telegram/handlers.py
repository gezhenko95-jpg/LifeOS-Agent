"""
Хендлеры Telegram-бота.

Свободный текст и одиночные команды («выполнил молоко», «привычка
чтение», добавление задачи) идут через ConversationEngine (Telegram-
агностичный, см. app/conversation/engine.py). Списки (`/tasks`,
`/habits`, `/goals` и их текстовые синонимы) отправляются напрямую с
inline-кнопками (app/telegram/keyboards.py) — ConversationEngine не
должен знать про Telegram-специфичные типы.
"""

import asyncio
import logging
import re

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.conversation.engine import ConversationEngine
from app.conversation.intent import Intent
from app.conversation.parser import parse_intent
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.drive.client import get_drive_client
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.insights.formatting import build_insights_text
from app.insights.service import InsightsService
from app.media_inbox.service import MediaInboxService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.proactive.repository import PendingPromptRepository
from app.proactive.service import PendingPromptService
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
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
    build_task_quick_actions_keyboard,
    build_tasks_message,
    build_watchlist_message,
)
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService

logger = logging.getLogger(__name__)

_ADD_TASK_HINT = "Окей, пиши, что за задача — с датой или без, я пойму."
_JOURNAL_PROMPT = "Что запишем в дневник? Пиши как есть — сохраню без изменений."

# Реплика ConversationEngine._add_task ("«{prefix}Добавил задачу: «{title}»…»")
# — по этому паттерну распознаём "движок только что создал задачу", чтобы
# прицепить быстрые кнопки (❗ Важно / 📅 Завтра), не меняя сам движок
# (он намеренно Telegram-агностичен, см. модуль-докстринг выше).
_TASK_CREATED_PATTERN = re.compile(r"^(?:❗ )?Добавил задачу: «(.+?)»")


def extract_created_task_title(reply: str) -> str | None:
    match = _TASK_CREATED_PATTERN.match(reply)
    return match.group(1) if match else None


_START_TEXT = (
    "Привет! Я LifeOS — помогаю не забывать задачи.\n"
    "Просто напишите, что нужно сделать, например «Завтра купить молоко», "
    "или воспользуйтесь меню снизу.\n"
    "Команда /help — что я умею.\n\n"
    "Ваш Telegram ID: {telegram_user_id}\n"
    "Впишите его в .env как owner_telegram_user_id, чтобы получать "
    "утренний брифинг."
)

# Постоянное меню (ReplyKeyboardMarkup, см. keyboards.py) — нажатие
# отправляет этот же текст обычным сообщением, поэтому просто матчим его
# точным сравнением до разбора естественного языка.
_MENU_ACTIONS = {
    MENU_TASKS: "tasks",
    MENU_HABITS: "habits",
    MENU_GOALS: "goals",
    MENU_ADD_TASK: "add_task",
    MENU_JOURNAL: "journal",
    MENU_INSIGHTS: "insights",
    MENU_WATCHLIST: "watchlist",
    MENU_SITE: "site",
    MENU_HELP: "help",
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    text = _START_TEXT.format(telegram_user_id=update.effective_user.id)
    await update.message.reply_text(text, reply_markup=build_main_menu())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переотправить постоянное меню.

    ReplyKeyboardMarkup живёт на клиенте, пока его не заменят новым —
    поэтому кнопка, добавленная в build_main_menu после последнего
    /start, у пользователя просто не появляется (так и не появилась
    «🌐 Сайт»). Раньше единственным способом обновить меню был /start,
    который вдобавок показывает приветствие для первой настройки.
    """
    if update.message is None:
        return
    await update.message.reply_text("Меню обновлено.", reply_markup=build_main_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_via_engine(update, context, "/help")


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_tasks_keyboard(update)


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_habits_keyboard(update)


async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_goals_keyboard(update)


async def handle_photo_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Фаза 2 Media Inbox (см. specs/010-media-inbox.md) — эскизы и
    скриншоты фильмов/книг автоматически раскладываются по Google Drive.
    Если Drive не настроен (нет token.json) — явно говорим об этом, а не
    молчим: пользователь мог не понять, что фото вообще не обработалось.

    После успешной загрузки оригинал фото удаляется из чата (файл уже
    на Диске, дублировать его в кеше Telegram незачем) — только при
    успехе, иначе фото потеряется, если Drive не смог его сохранить."""
    if update.message is None or not update.message.photo:
        return
    if update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    # Построение клиента читает token.json с диска — блокирующая операция,
    # как и сами вызовы Drive API (см. MediaInboxService._upload_to_drive).
    drive_client = await asyncio.to_thread(get_drive_client)
    if drive_client is None:
        await update.message.reply_text(
            "Media Inbox ещё не настроен (нет token.json на сервере)."
        )
        return

    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.UPLOAD_PHOTO
    )

    photo = update.message.photo[-1]  # последний элемент — самое большое разрешение
    file = await context.bot.get_file(photo.file_id)
    content = bytes(await file.download_as_bytearray())
    filename = f"{photo.file_unique_id}.jpg"

    async with AsyncSessionLocal() as session:
        service = MediaInboxService(
            drive_client,
            WatchlistService(WatchlistRepository(session)),
            get_ai_client(),
        )
        saved, reply = await service.handle_photo(
            telegram_user_id, filename, content, "image/jpeg"
        )

    if saved:
        try:
            await update.message.delete()
        except Exception:
            # Не критично — файл уже на Диске, просто оригинал останется
            # в чате (например, если сообщение старше 48 часов).
            logger.warning("Не удалось удалить фото-сообщение после загрузки")
        await context.bot.send_message(chat_id=telegram_user_id, text=reply)
    else:
        await update.message.reply_text(reply)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.message.text is None:
        return

    text = update.message.text

    menu_action = _MENU_ACTIONS.get(text)
    if menu_action == "tasks":
        await _send_tasks_keyboard(update)
        return
    if menu_action == "habits":
        await _send_habits_keyboard(update)
        return
    if menu_action == "goals":
        await _send_goals_keyboard(update)
        return
    if menu_action == "help":
        await _reply_via_engine(update, context, "/help")
        return
    if menu_action == "add_task":
        # Заодно переотправляем меню: ReplyKeyboardMarkup живёт на
        # клиенте, пока его не заменят, поэтому кнопка, добавленная после
        # последнего /start, у пользователя просто не появляется — так и
        # не появилась «🌐 Сайт». Этот ответ не несёт inline-кнопок, а
        # значит место под клавиатуру свободно (две разом Telegram не
        # принимает).
        await update.message.reply_text(_ADD_TASK_HINT, reply_markup=build_main_menu())
        return
    if menu_action == "journal":
        await _open_journal_prompt(update)
        return
    if menu_action == "insights":
        await _send_insights(update)
        return
    if menu_action == "watchlist":
        await _send_watchlist_keyboard(update)
        return
    if menu_action == "site":
        await _send_site_link(update)
        return

    intent = parse_intent(text).intent
    if intent is Intent.LIST_TASKS:
        await _send_tasks_keyboard(update)
        return
    if intent is Intent.LIST_HABITS:
        await _send_habits_keyboard(update)
        return
    if intent is Intent.LIST_WATCHLIST:
        await _send_watchlist_keyboard(update)
        return

    await _reply_via_engine(update, context, text)


async def _send_tasks_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = TaskService(TaskRepository(session))
        tasks = await service.list_active_tasks(telegram_user_id)
        text, markup = build_tasks_message(tasks)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_habits_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = HabitService(HabitRepository(session))
        habits = await service.list_active_habits(telegram_user_id)
        streaks = {habit.id: await service.get_streak(habit.id) for habit in habits}
        text, markup = build_habits_message(habits, streaks)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_goals_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = GoalService(GoalRepository(session))
        goals = await service.list_active_goals(telegram_user_id)
        text, markup = build_goals_message(goals)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_watchlist_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = WatchlistService(WatchlistRepository(session))
        items = await service.list_active_items(telegram_user_id)
        text, markup = build_watchlist_message(items)

    await update.message.reply_text(
        text, reply_markup=markup, parse_mode=ParseMode.HTML
    )


async def _send_site_link(update: Update) -> None:
    """Кнопка «🌐 Сайт» — ReplyKeyboardMarkup не умеет открывать ссылки
    напрямую, поэтому в ответ шлём сообщение с inline-кнопкой
    (InlineKeyboardButton(url=...), см. keyboards.py). Пусто в настройках
    — значит /ui ещё не задеплоен на публичный адрес, говорим прямо."""
    if update.message is None:
        return
    url = get_settings().public_ui_url
    if not url:
        await update.message.reply_text("Сайт ещё не настроен (нет публичного адреса).")
        return
    await update.message.reply_text(
        "Полный интерфейс:", reply_markup=build_open_site_keyboard(url)
    )


async def _send_insights(update: Update) -> None:
    """Кнопка «📊 Инсайты» — Personal Insights по запросу (см.
    specs/009-personal-insights.md). В отличие от фоновой месячной
    рассылки (app/telegram/jobs.py::send_monthly_insights_job), здесь
    отвечаем всегда, даже если находок нет — пользователь сам спросил."""
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = InsightsService(
            TaskService(TaskRepository(session)),
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
        )
        findings = await service.build_findings(telegram_user_id)

    await update.message.reply_text(build_insights_text(findings))


async def _open_journal_prompt(update: Update) -> None:
    """Кнопка «📝 Дневник» — вручную открывает дневниковый pending
    (в отличие от проактивных вопросов, здесь нет gap-detection выбора
    категории — пользователь сам решил писать в дневник прямо сейчас).
    Следующее сообщение уйдёт в дневник без префикса "дневник:" — см.
    ConversationEngine._try_capture_journal."""
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        await PendingPromptRepository(session).upsert(
            telegram_user_id, "journal", _JOURNAL_PROMPT
        )

    await update.message.reply_text(_JOURNAL_PROMPT)


async def _reply_via_engine(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    if update.message is None or update.effective_user is None:
        return

    telegram_user_id = update.effective_user.id

    # AI-вызовы (fallback-разбор, ответ на проактивный вопрос) занимают
    # секунду-две — "печатает…" даёт понять, что бот не завис.
    await context.bot.send_chat_action(
        chat_id=telegram_user_id, action=ChatAction.TYPING
    )

    async with AsyncSessionLocal() as session:
        task_service = TaskService(TaskRepository(session))
        engine = ConversationEngine(
            task_service,
            HabitService(HabitRepository(session)),
            MemoryService(MemoryRepository(session)),
            ai_client=get_ai_client(),
            goal_service=GoalService(GoalRepository(session)),
            pending_prompt_service=PendingPromptService(
                PendingPromptRepository(session),
                GoalService(GoalRepository(session)),
                HabitService(HabitRepository(session)),
                MemoryService(MemoryRepository(session)),
            ),
            watchlist_service=WatchlistService(WatchlistRepository(session)),
        )
        reply = await engine.handle_message(telegram_user_id, text)

        markup = None
        created_title = extract_created_task_title(reply)
        if created_title:
            matches = await task_service.find_active_by_title(
                telegram_user_id, created_title
            )
            if matches:
                # Нужна именно только что созданная задача — а не первая
                # по времени, как в find_active_by_title для complete/delete
                # (см. flows/003-manage-tasks.md), иначе кнопки могли бы
                # прицепиться к старой одноимённой задаче.
                newest = max(matches, key=lambda t: t.created_at)
                markup = build_task_quick_actions_keyboard(newest)

    # Если inline-кнопок нет, место под клавиатуру свободно — освежаем
    # постоянное меню. Telegram не принимает inline- и reply-клавиатуру в
    # одном сообщении, поэтому только в этой ветке. Пользователь разницы
    # не видит (меню заменяется таким же), зато новые кнопки появляются
    # сами, без /start и /menu.
    await update.message.reply_text(reply, reply_markup=markup or build_main_menu())
