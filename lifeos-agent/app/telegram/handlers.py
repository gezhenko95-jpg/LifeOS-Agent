"""
Хендлеры Telegram-бота.

Свободный текст и одиночные команды («выполнил молоко», «привычка
чтение», добавление задачи) идут через ConversationEngine (Telegram-
агностичный, см. app/conversation/engine.py). Списки (`/tasks`,
`/habits`, `/goals` и их текстовые синонимы) отправляются напрямую с
inline-кнопками (app/telegram/keyboards.py) — ConversationEngine не
должен знать про Telegram-специфичные типы.
"""

import re

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.ai.client import get_ai_client
from app.conversation.engine import ConversationEngine
from app.conversation.intent import Intent
from app.conversation.parser import parse_intent
from app.db.session import AsyncSessionLocal
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.proactive.repository import PendingPromptRepository
from app.proactive.service import PendingPromptService
from app.tasks.repository import TaskRepository
from app.tasks.service import TaskService
from app.telegram.keyboards import (
    MENU_GOALS,
    MENU_HABITS,
    MENU_HELP,
    MENU_TASKS,
    build_goals_message,
    build_habits_message,
    build_main_menu,
    build_task_quick_actions_keyboard,
    build_tasks_message,
)

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
    MENU_HELP: "help",
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    text = _START_TEXT.format(telegram_user_id=update.effective_user.id)
    await update.message.reply_text(text, reply_markup=build_main_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_via_engine(update, context, "/help")


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_tasks_keyboard(update)


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_habits_keyboard(update)


async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_goals_keyboard(update)


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

    intent = parse_intent(text).intent
    if intent is Intent.LIST_TASKS:
        await _send_tasks_keyboard(update)
        return
    if intent is Intent.LIST_HABITS:
        await _send_habits_keyboard(update)
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

    await update.message.reply_text(text, reply_markup=markup)


async def _send_habits_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = HabitService(HabitRepository(session))
        habits = await service.list_active_habits(telegram_user_id)
        streaks = {habit.id: await service.get_streak(habit.id) for habit in habits}
        text, markup = build_habits_message(habits, streaks)

    await update.message.reply_text(text, reply_markup=markup)


async def _send_goals_keyboard(update: Update) -> None:
    if update.message is None or update.effective_user is None:
        return
    telegram_user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        service = GoalService(GoalRepository(session))
        goals = await service.list_active_goals(telegram_user_id)
        text, markup = build_goals_message(goals)

    await update.message.reply_text(text, reply_markup=markup)


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

    await update.message.reply_text(reply, reply_markup=markup)
