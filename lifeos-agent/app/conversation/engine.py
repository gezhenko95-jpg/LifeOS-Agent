"""
Conversation Engine.

Связывает разбор намерения с Tasks/Habits/Goals/Memory Service. Основной
путь — rule-based parser.py (быстро, бесплатно, предсказуемо).

Два AI-фолбэка для ADD_TASK-подобного (нераспознанного правилами) текста,
в порядке проверки:
1. Если есть открытый проактивный вопрос (pending_prompt_service, см.
   specs/006-proactive-engagement.md) — попытка понять text как ответ на
   него (_try_answer_pending_prompt).
2. Если ADD_TASK с пустым title — попытка через AI Service разобрать
   намерение целиком (ai_fallback.py, см. specs/003-conversation.md).
Оба — тихий fallback: любая ошибка AI не показывается пользователю.
"""

from datetime import datetime

from app.ai.client import AIClient
from app.conversation.ai_fallback import parse_intent_with_ai
from app.conversation.intent import Intent, ParsedIntent
from app.conversation.parser import parse_intent
from app.goals.service import GoalService
from app.habits.models import Habit
from app.habits.service import HabitService
from app.memory.models import MemoryType
from app.memory.service import MemoryService
from app.proactive.ai_extract import extract_prompt_answer
from app.proactive.service import PendingPromptService
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
    "• спросить про день — «что на завтра», «какие задачи в пятницу»\n"
    "• вспомнить — «напомни, что я говорил про отпуск»\n"
    "• дневник — «дневник: как прошёл день» (запомню в памяти)\n"
    "• иногда я сам спрашиваю о целях/привычках/проектах — просто "
    "ответьте текстом, и я запомню это как надо\n"
    "• /tasks, /habits, /goals — списки с кнопками прямо под сообщением"
)

_MAX_RECALL_RESULTS = 5
_STREAK_MILESTONES = {7, 30, 100}


class ConversationEngine:
    def __init__(
        self,
        task_service: TaskService,
        habit_service: HabitService,
        memory_service: MemoryService,
        ai_client: AIClient | None = None,
        goal_service: GoalService | None = None,
        pending_prompt_service: PendingPromptService | None = None,
    ) -> None:
        self._tasks = task_service
        self._habits = habit_service
        self._memory = memory_service
        self._ai_client = ai_client
        self._goals = goal_service
        self._pending_prompts = pending_prompt_service

    async def handle_message(self, telegram_user_id: int, text: str) -> str:
        parsed = parse_intent(text)

        if (
            parsed.intent is Intent.ADD_TASK
            and self._pending_prompts is not None
            and self._ai_client is not None
        ):
            prompt_reply = await self._try_answer_pending_prompt(telegram_user_id, text)
            if prompt_reply is not None:
                return prompt_reply

        if (
            parsed.intent is Intent.ADD_TASK
            and not parsed.title
            and self._ai_client is not None
        ):
            ai_parsed = await parse_intent_with_ai(text, self._ai_client)
            if ai_parsed is not None:
                parsed = ai_parsed

        return await self._dispatch(telegram_user_id, parsed)

    async def _try_answer_pending_prompt(
        self, telegram_user_id: int, text: str
    ) -> str | None:
        """Если открыт проактивный вопрос — попробовать понять text как ответ.

        None означает "не обработано как ответ" — вызывающий код должен
        продолжить обычную обработку text (в т.ч. создать задачу, если это
        и правда просто новая задача, а не ответ на вопрос). Pending
        намеренно НЕ чистится при None — вопрос остаётся открытым до
        следующего успешного ответа или следующего запланированного
        вопроса (см. PendingPromptService.pick_and_open).
        """
        assert self._pending_prompts is not None and self._ai_client is not None

        pending = await self._pending_prompts.get_open(telegram_user_id)
        if pending is None:
            return None

        answer = await extract_prompt_answer(
            pending.category, pending.question_text, text, self._ai_client
        )
        if answer is None or answer.action == "unrelated":
            return None

        # Клиру откладываем до момента, когда точно знаем, что можем
        # обработать action — иначе при "action верный, но title/content
        # пустые" вопрос потерялся бы без результата (см. ai_extract.py).
        if answer.action == "create_goal" and answer.title and self._goals:
            await self._pending_prompts.clear(telegram_user_id)
            goal = await self._goals.create_goal(
                telegram_user_id, answer.title, answer.target_date
            )
            return f"Добавил цель «{goal.title}» 🎯"

        if answer.action == "create_habit" and answer.title:
            await self._pending_prompts.clear(telegram_user_id)
            habit = await self._habits.create_habit(telegram_user_id, answer.title)
            return f"Добавил привычку «{habit.title}» 🔁"

        if answer.action == "save_memory" and answer.memory_type and answer.content:
            await self._pending_prompts.clear(telegram_user_id)
            await self._memory.save(
                telegram_user_id,
                MemoryType(answer.memory_type),
                answer.content,
                source="proactive_prompt",
            )
            return f"Запомнил: {answer.content} 📝"

        return None

    async def _dispatch(self, telegram_user_id: int, parsed: ParsedIntent) -> str:
        if parsed.intent is Intent.HELP:
            return _HELP_TEXT
        if parsed.intent is Intent.LIST_TASKS:
            return await self._list_tasks(telegram_user_id)
        if parsed.intent is Intent.QUERY_TASKS_BY_DATE:
            return await self._list_tasks_by_date(telegram_user_id, parsed.due_date)
        if parsed.intent is Intent.RECALL:
            return await self._recall(telegram_user_id, parsed.title or "")
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

    async def _list_tasks_by_date(
        self, telegram_user_id: int, due_date: datetime | None
    ) -> str:
        if due_date is None:
            return await self._list_tasks(telegram_user_id)

        tasks = await self._tasks.list_active_tasks(telegram_user_id)
        target = due_date.date()
        matches = [t for t in tasks if t.due_date and t.due_date.date() == target]
        label = f"{target:%d.%m.%Y}"
        if not matches:
            return f"На {label} задач нет."

        lines = [f"Задачи на {label}:"]
        for index, task in enumerate(matches, start=1):
            prefix = "❗ " if task.priority == "high" else ""
            lines.append(f"{index}. {prefix}{task.title}")
        return "\n".join(lines)

    async def _recall(self, telegram_user_id: int, query: str) -> str:
        if not query:
            return "Что напомнить? Например: «напомни, что я говорил про отпуск»."

        entries = await self._memory.search(telegram_user_id, query)
        if not entries:
            return f"Ничего не нашёл про «{query}»."

        lines = [f"Нашёл по «{query}»:"]
        lines.extend(f"• {entry.content}" for entry in entries[:_MAX_RECALL_RESULTS])
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
        celebration = (
            f"\n\n🎉 {streak} дней подряд — солидная серия!"
            if streak in _STREAK_MILESTONES
            else ""
        )
        return f"Готово: «{habit.title}» — 🔥 {streak} дней подряд.{celebration}{note}"

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
