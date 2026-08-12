"""
Conversation Engine.

Связывает разбор намерения с Tasks Service. Основной путь — rule-based
parser.py (быстро, бесплатно, предсказуемо). Если он не смог понять
сообщение (ADD_TASK с пустым title) и передан ai_client — делается
одна попытка через AI Service (ai_fallback.py, см.
specs/003-conversation.md) перед тем, как признать сообщение непонятым.
"""

from app.ai.client import AIClient
from app.conversation.ai_fallback import parse_intent_with_ai
from app.conversation.intent import Intent, ParsedIntent
from app.conversation.parser import parse_intent
from app.habits.models import Habit
from app.habits.service import HabitService
from app.memory.models import MemoryType
from app.memory.service import MemoryService
from app.tasks.models import Task
from app.tasks.service import TaskService

_HELP_TEXT = (
    "Я умею:\n"
    "• запомнить задачу — просто напишите её, например «Завтра купить молоко»\n"
    "• показать список — «покажи задачи»\n"
    "• отметить выполненной — «выполнил купить молоко»\n"
    "• удалить — «удали купить молоко»\n"
    "• привычки — «привычки» (список со стриком), «привычка чтение» "
    "(отметить сегодня)\n"
    "• дневник — «дневник: как прошёл день» (запомню в памяти)\n"
    "• /tasks, /habits, /goals — списки с кнопками прямо под сообщением"
)


class ConversationEngine:
    def __init__(
        self,
        task_service: TaskService,
        habit_service: HabitService,
        memory_service: MemoryService,
        ai_client: AIClient | None = None,
    ) -> None:
        self._tasks = task_service
        self._habits = habit_service
        self._memory = memory_service
        self._ai_client = ai_client

    async def handle_message(self, telegram_user_id: int, text: str) -> str:
        parsed = parse_intent(text)

        if (
            parsed.intent is Intent.ADD_TASK
            and not parsed.title
            and self._ai_client is not None
        ):
            ai_parsed = await parse_intent_with_ai(text, self._ai_client)
            if ai_parsed is not None:
                parsed = ai_parsed

        return await self._dispatch(telegram_user_id, parsed)

    async def _dispatch(self, telegram_user_id: int, parsed: ParsedIntent) -> str:
        if parsed.intent is Intent.HELP:
            return _HELP_TEXT
        if parsed.intent is Intent.LIST_TASKS:
            return await self._list_tasks(telegram_user_id)
        if parsed.intent is Intent.COMPLETE_TASK:
            return await self._complete_task(telegram_user_id, parsed.title or "")
        if parsed.intent is Intent.DELETE_TASK:
            return await self._delete_task(telegram_user_id, parsed.title or "")
        if parsed.intent is Intent.LIST_HABITS:
            return await self._list_habits(telegram_user_id)
        if parsed.intent is Intent.HABIT_DONE:
            return await self._habit_done(telegram_user_id, parsed.title or "")
        if parsed.intent is Intent.JOURNAL_ENTRY:
            return await self._journal_entry(telegram_user_id, parsed.title or "")
        return await self._add_task(telegram_user_id, parsed)

    async def _add_task(self, telegram_user_id: int, parsed: ParsedIntent) -> str:
        if not parsed.title:
            return (
                "Не понял, какую задачу добавить. "
                "Напишите, например: «Завтра купить молоко»."
            )
        task = await self._tasks.create_task(
            telegram_user_id, parsed.title, parsed.due_date, parsed.priority
        )
        prefix = "❗ " if task.priority == "high" else ""
        if task.due_date:
            return f"{prefix}Добавил задачу: «{task.title}» на {task.due_date:%d.%m.%Y}"
        return f"{prefix}Добавил задачу: «{task.title}»"

    async def _list_tasks(self, telegram_user_id: int) -> str:
        tasks = await self._tasks.list_active_tasks(telegram_user_id)
        if not tasks:
            return "Активных задач нет."
        lines = []
        for index, task in enumerate(tasks, start=1):
            prefix = "❗ " if task.priority == "high" else ""
            suffix = f" — {task.due_date:%d.%m.%Y}" if task.due_date else ""
            lines.append(f"{index}. {prefix}{task.title}{suffix}")
        return "\n".join(lines)

    async def _complete_task(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую задачу отметить выполненной?"
        matches = await self._tasks.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"Не нашёл активную задачу «{title_query}»."
        task = await self._tasks.complete_task_by_title(telegram_user_id, title_query)
        if task is None:
            return f"Не нашёл активную задачу «{title_query}»."
        note = _ambiguity_note(matches, title_query)
        return f"Готово: «{task.title}» отмечена выполненной.{note}"

    async def _delete_task(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую задачу удалить?"
        matches = await self._tasks.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"Не нашёл активную задачу «{title_query}»."
        task = await self._tasks.delete_task_by_title(telegram_user_id, title_query)
        if task is None:
            return f"Не нашёл активную задачу «{title_query}»."
        note = _ambiguity_note(matches, title_query)
        return f"Удалил задачу «{task.title}».{note}"

    async def _list_habits(self, telegram_user_id: int) -> str:
        habits = await self._habits.list_active_habits(telegram_user_id)
        if not habits:
            return "Активных привычек нет."
        lines = []
        for index, habit in enumerate(habits, start=1):
            streak = await self._habits.get_streak(habit.id)
            suffix = f" — 🔥 {streak} дней подряд" if streak > 0 else ""
            lines.append(f"{index}. {habit.title}{suffix}")
        return "\n".join(lines)

    async def _habit_done(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую привычку отметить выполненной?"
        matches = await self._habits.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"Не нашёл активную привычку «{title_query}»."
        habit = await self._habits.mark_done_today(telegram_user_id, title_query)
        if habit is None:
            return f"Не нашёл активную привычку «{title_query}»."
        streak = await self._habits.get_streak(habit.id)
        note = _ambiguity_note(matches, title_query)
        return f"Готово: «{habit.title}» — 🔥 {streak} дней подряд.{note}"

    async def _journal_entry(self, telegram_user_id: int, content: str) -> str:
        if not content:
            return "Что записать в дневник? Например: «дневник: продуктивный день»."
        await self._memory.save(
            telegram_user_id, MemoryType.JOURNAL, content, source="telegram"
        )
        return "Записал в дневник."


def _ambiguity_note(matches: list[Task] | list[Habit], title_query: str) -> str:
    """Предупреждение, если под подстроку подошло больше одной задачи.

    Берётся первая по времени создания (см. TaskService), остальные —
    просто перечисляются, чтобы пользователь мог написать точнее.
    См. flows/003-manage-tasks.md.
    """
    if len(matches) <= 1:
        return ""
    others = ", ".join(f"«{task.title}»" for task in matches[1:])
    return (
        f"\n\nПод «{title_query}» подошло ещё {len(matches) - 1}: {others}. "
        "Если это не та задача — напишите название точнее."
    )
