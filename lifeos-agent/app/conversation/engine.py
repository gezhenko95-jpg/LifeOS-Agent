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

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
from app.tasks.formatting import format_due_human, task_created_prefix
from app.tasks.models import Task
from app.tasks.service import TaskService
from app.watchlist.models import MEDIA_TYPE_EMOJI
from app.watchlist.service import WatchlistService


@dataclass(frozen=True)
class EngineResult:
    """Ответ движка: текст + опционально только что созданная задача.

    Раньше handlers.py распознавал «задача создана» regex'ом по тексту
    ответа (`_TASK_CREATED_PATTERN`) и заново шёл в БД за задачей через
    find_active_by_title — притом что движок уже держал объект Task в
    руках. Хрупкая связка (см. AUDIT.md, A-4): поменяй формулировку
    «Добавил задачу: …» — кнопки молча исчезнут, тесты этого не увидят.
    """

    text: str
    created_task: Task | None = None


_HELP_TEXT = (
    "Я умею:\n"
    "• запомнить задачу — просто напишите её, например «Завтра купить молоко»\n"
    "• показать список — «покажи задачи»\n"
    "• отметить выполненной — «выполнил купить молоко»\n"
    "• удалить — «удали купить молоко»\n"
    "• привычки — «привычки» (список со стриком), «привычка чтение» "
    "(отметить сегодня)\n"
    "• спросить про день — «что на завтра», «какие задачи в пятницу»\n"
    "• напоминание ко времени — «напомни в 19:00 позвонить маме», "
    "«напомни завтра в 9 сдать отчёт», «напомни через пару часов выйти»\n"
    "• вспомнить — «напомни, что я говорил про отпуск»\n"
    "• повторяющиеся задачи — «каждый понедельник оплатить интернет», "
    "«каждый день пить воду»\n"
    "• дневник — «дневник: как прошёл день» (запомню в памяти), или "
    "нажмите «📝 Дневник» в меню — и пишите без префикса\n"
    "• посмотреть/прочитать позже — «посмотреть фильм Дюна», «книга X», "
    "или кнопка «🎬 Посмотреть» в меню; «список книг»/«список фильмов»/"
    "«полка» — показать список\n"
    "• иногда я сам спрашиваю о целях/привычках/проектах или прошу "
    "дневник — просто ответьте текстом, и я запомню это как надо\n"
    "• всё это есть в меню снизу и работает одинаково: любая кнопка "
    "раздела открывает экран с «Список» и «➕ Добавить» — дальше только "
    "нажатия, команды помнить не нужно\n"
    "• дайджест каналов — «/digest_new ESG daily» (создать тему), "
    "«/digest_add ESG channelname» (добавить публичный канал), "
    "«/digest_list» (что есть), «/digest ESG» (саммари новых постов "
    "прямо сейчас)\n"
    "• /tasks, /habits, /goals — списки с кнопками прямо под сообщением"
)

_MAX_RECALL_RESULTS = 5
_STREAK_MILESTONES = {7, 30, 100}
# Если AI не смог связать ответ с открытым вопросом, а вопрос был задан
# недавно — пользователю стоит подсказать, что ответ "потерялся", а не
# молча создавать задачу без объяснений. Если вопрос уже старый — скорее
# всего пользователь и не пытался на него отвечать, подсказка будет
# только раздражать (см. историю с "Сохрани лес" → задача без объяснений).
#
# 30 минут (прежнее значение) оказались слишком жёстким порогом на
# живом использовании: утренний вопрос "что снилось?" задаётся в 10:30,
# а ответ на него пришёл в 12:56 — 2ч26м спустя, окно уже истекло, и
# ответ ("ничего не снилось, я вчера перепил") улетел в обычный разбор
# и создал бессмысленную задачу без срока. Слоты дня разнесены на
# 3.5–5 часов (10:30 → 14:00 → 19:00 → 21:00, см.
# flows/009-daily-rhythm.md), и КАЖДЫЙ следующий слот перезаписывает
# pending_prompt (upsert) вместе с asked_at — то есть "истекание" внутри
# одного и того же дня не нужно ждать от этого окна вообще: как только
# наступит следующий слот, вопрос сам обновится. Единственная реальная
# роль окна — не превращать в дневник случайную команду, отправленную
# через несколько дней после того, как пользователь читал последний
# вопрос и забыл на него ответить.
_UNANSWERED_PROMPT_NOTE_WINDOW = timedelta(hours=6)

# Слова, с которых начинается ЯВНАЯ команда боту, а не дневниковая запись
# (см. _try_capture_journal). Проверяется только начало сообщения:
# «напомни» внутри длинной прозы — обычное слово, а в начале — просьба.
_COMMAND_PREFIXES = ("напомни", "напомнить", "вспомни")


def _starts_with_command(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith("/"):
        return True
    lowered = stripped.lower()
    return any(lowered.startswith(prefix) for prefix in _COMMAND_PREFIXES)


class ConversationEngine:
    def __init__(
        self,
        task_service: TaskService,
        habit_service: HabitService,
        memory_service: MemoryService,
        ai_client: AIClient | None = None,
        goal_service: GoalService | None = None,
        pending_prompt_service: PendingPromptService | None = None,
        watchlist_service: WatchlistService | None = None,
    ) -> None:
        self._tasks = task_service
        self._habits = habit_service
        self._memory = memory_service
        self._ai_client = ai_client
        self._goals = goal_service
        self._pending_prompts = pending_prompt_service
        self._watchlist = watchlist_service

    async def handle_message(
        self,
        telegram_user_id: int,
        text: str,
        parsed: ParsedIntent | None = None,
    ) -> EngineResult:
        """`parsed` — если вызывающий код (handlers.py) уже разобрал text
        сам (например, чтобы решить, не LIST_TASKS/LIST_HABITS/
        LIST_WATCHLIST ли это, для Telegram-специфичной клавиатуры), можно
        передать готовый результат — раньше `parse_intent` вызывался
        дважды на одно и то же сообщение (см. AUDIT.md, A-5). Если
        `_try_capture_journal` ниже перехватит сообщение — переданный
        `parsed` просто не используется, не проблема (разбор дешёвый,
        rule-based, без сети)."""
        if self._pending_prompts is not None:
            journal_reply = await self._try_capture_journal(telegram_user_id, text)
            if journal_reply is not None:
                return EngineResult(journal_reply)

        if parsed is None:
            parsed = parse_intent(text)
        unanswered_question: str | None = None

        if (
            parsed.intent is Intent.ADD_TASK
            and self._pending_prompts is not None
            and self._ai_client is not None
        ):
            prompt_reply, unanswered_question = await self._try_answer_pending_prompt(
                telegram_user_id, text
            )
            if prompt_reply is not None:
                return EngineResult(prompt_reply)

        if (
            parsed.intent is Intent.ADD_TASK
            and not parsed.title
            and self._ai_client is not None
        ):
            ai_parsed = await parse_intent_with_ai(text, self._ai_client)
            if ai_parsed is not None:
                parsed = ai_parsed

        result = await self._dispatch(telegram_user_id, parsed)
        if unanswered_question is not None:
            result = EngineResult(
                text=result.text
                + (
                    f"\n\n(Не понял это как ответ на «{unanswered_question}» — "
                    "если хотел ответить, напиши ещё раз.)"
                ),
                created_task=result.created_task,
            )
        return result

    async def _try_capture_journal(
        self, telegram_user_id: int, text: str
    ) -> str | None:
        """Если открыт дневниковый вопрос (сон/факт/итоги дня, или кнопка
        «📝 Дневник» — см. app/telegram/handlers.py) — сохранить text как
        есть, БЕЗ разбора через parse_intent/AI.

        Проверяется РАНЬШЕ parse_intent (не только для ADD_TASK, как
        structured-вопросы про цели/привычки ниже) — иначе длинная
        дневниковая проза со случайным словом вроде "сделал"/"привычка"
        внутри предложения улетела бы в COMPLETE_TASK/HABIT_DONE вместо
        дневника. Весь ответ ЦЕЛИКОМ — это и есть запись, разбирать нечего.

        Если вопрос устарел (> _UNANSWERED_PROMPT_NOTE_WINDOW) — тихо не
        перехватываем: дневниковое приглашение необязательное, в отличие
        от structured-вопросов не считаем это "промахом" пользователя
        (без пометки "не понял").

        Явные команды не перехватываются никогда — ни "/help", ни
        "напомни в 9 утра запустить стиралку". Оба случая пойманы на
        живом использовании: в боевой БД оказались дневниковые записи
        "/help" и "напомни сегодня в 9 утра запустить стиралку", то есть
        ни справка, ни напоминание не сработали, а текст молча ушёл в
        дневник (см. AUDIT.md, B-1).

        Проза дневника при этом по-прежнему перехватывается целиком:
        отсеиваются только сообщения, НАЧИНАЮЩИЕСЯ с командного слова
        (см. _COMMAND_PREFIXES), а не содержащие его где-то внутри —
        иначе фраза «мне снилось, что я выполнил марафон» снова улетела
        бы в задачи вместо дневника.
        """
        assert self._pending_prompts is not None

        if _starts_with_command(text):
            return None

        pending = await self._pending_prompts.get_open(telegram_user_id)
        if pending is None or pending.category != "journal":
            return None

        is_fresh = (
            datetime.now(timezone.utc) - pending.asked_at
        ) <= _UNANSWERED_PROMPT_NOTE_WINDOW
        if not is_fresh:
            return None

        await self._pending_prompts.clear(telegram_user_id)
        await self._memory.save(
            telegram_user_id, MemoryType.JOURNAL, text, source="quick_capture"
        )
        return "📝 Записал в дневник."

    async def _try_answer_pending_prompt(
        self, telegram_user_id: int, text: str
    ) -> tuple[str | None, str | None]:
        """Если открыт проактивный вопрос — попробовать понять text как ответ.

        Возвращает (handled_reply, unanswered_question):
        - handled_reply не None → ответ успешно распознан, вернуть его как
          финальный ответ пользователю.
        - unanswered_question не None → был открытый вопрос, но text не
          удалось связать с ним (и вопрос задан недавно — см.
          _UNANSWERED_PROMPT_NOTE_WINDOW); вызывающий код допишет к
          обычному ответу пояснение, чтобы пользователь не терялся в
          догадках, почему бот "не услышал" его ответ (см. историю с
          "Сохрани лес" → тихое создание задачи).

        Pending намеренно НЕ чистится, если ответ не распознан — вопрос
        остаётся открытым до следующего успешного ответа или следующего
        запланированного вопроса (см. PendingPromptService.pick_morning_reflection
        / pick_gap_question_if_any, которые перезаписывают его через upsert).
        """
        assert self._pending_prompts is not None and self._ai_client is not None

        pending = await self._pending_prompts.get_open(telegram_user_id)
        if pending is None:
            return None, None

        is_fresh = (
            datetime.now(timezone.utc) - pending.asked_at
        ) <= _UNANSWERED_PROMPT_NOTE_WINDOW

        answer = await extract_prompt_answer(
            pending.category, pending.question_text, text, self._ai_client
        )
        if answer is None or answer.action == "unrelated":
            return None, (pending.question_text if is_fresh else None)

        # Клиру откладываем до момента, когда точно знаем, что можем
        # обработать action — иначе при "action верный, но title/content
        # пустые" вопрос потерялся бы без результата (см. ai_extract.py).
        if answer.action == "create_goal" and answer.title and self._goals:
            await self._pending_prompts.clear(telegram_user_id)
            goal = await self._goals.create_goal(
                telegram_user_id, answer.title, answer.target_date
            )
            return f"🎯 Новая цель: «{goal.title}»", None

        if answer.action == "create_habit" and answer.title:
            await self._pending_prompts.clear(telegram_user_id)
            habit = await self._habits.create_habit(telegram_user_id, answer.title)
            return f"🔁 Новая привычка: «{habit.title}»", None

        if answer.action == "save_memory" and answer.memory_type and answer.content:
            await self._pending_prompts.clear(telegram_user_id)
            await self._memory.save(
                telegram_user_id,
                MemoryType(answer.memory_type),
                answer.content,
                source="proactive_prompt",
            )
            return f"🧠 Запомнил: {answer.content}", None

        return None, (pending.question_text if is_fresh else None)

    async def _dispatch(
        self, telegram_user_id: int, parsed: ParsedIntent
    ) -> EngineResult:
        if parsed.intent is Intent.HELP:
            return EngineResult(_HELP_TEXT)
        if parsed.intent is Intent.LIST_TASKS:
            return EngineResult(await self._list_tasks(telegram_user_id))
        if parsed.intent is Intent.QUERY_TASKS_BY_DATE:
            return EngineResult(
                await self._list_tasks_by_date(telegram_user_id, parsed.due_date)
            )
        if parsed.intent is Intent.RECALL:
            return EngineResult(
                await self._recall(telegram_user_id, parsed.title or "")
            )
        if parsed.intent is Intent.COMPLETE_TASK:
            return EngineResult(
                await self._complete_task(telegram_user_id, parsed.title or "")
            )
        if parsed.intent is Intent.DELETE_TASK:
            return EngineResult(
                await self._delete_task(telegram_user_id, parsed.title or "")
            )
        if parsed.intent is Intent.LIST_HABITS:
            return EngineResult(await self._list_habits(telegram_user_id))
        if parsed.intent is Intent.HABIT_DONE:
            return EngineResult(
                await self._habit_done(telegram_user_id, parsed.title or "")
            )
        if parsed.intent is Intent.JOURNAL_ENTRY:
            return EngineResult(
                await self._journal_entry(telegram_user_id, parsed.title or "")
            )
        if parsed.intent is Intent.ADD_WATCHLIST_ITEM:
            return await self._add_watchlist_item(telegram_user_id, parsed)
        if parsed.intent is Intent.LIST_WATCHLIST:
            return EngineResult(await self._list_watchlist(telegram_user_id))
        text, task = await self._add_task(telegram_user_id, parsed)
        return EngineResult(text, task)

    async def _add_task(
        self, telegram_user_id: int, parsed: ParsedIntent
    ) -> tuple[str, Task | None]:
        if not parsed.title:
            return (
                "Не понял, какую задачу добавить. "
                "Напишите, например: «Завтра купить молоко».",
                None,
            )
        task = await self._tasks.create_task(
            telegram_user_id,
            parsed.title,
            parsed.due_date,
            parsed.priority,
            parsed.recurrence,
        )
        prefix_line = task_created_prefix(task)
        repeat = "  🔁 повторяется" if task.recurrence else ""
        if task.due_date:
            text = f"{prefix_line}\n🕘 {format_due_human(task.due_date)}{repeat}"
        else:
            text = f"{prefix_line}\n🗓 без срока{repeat}"
        return text, task

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
            return f"На {label} задач нет. 🌤"

        lines = [f"Задачи на {label}:"]
        for index, task in enumerate(matches, start=1):
            prefix = "❗ " if task.priority == "high" else ""
            lines.append(f"{index}. {prefix}{task.title}")
        return "\n".join(lines)

    async def _recall(self, telegram_user_id: int, query: str) -> str:
        if not query:
            return "Что напомнить? Например: «напомни, что я говорил про отпуск»."

        entries = await self._memory.search(telegram_user_id, query)
        header = f"Нашёл по «{query}»:"

        if not entries and self._ai_client is not None:
            # Буквальный поиск ничего не нашёл — пробуем смысловой (см.
            # specs/011-semantic-memory-search.md). Другая вводная фраза —
            # чтобы не выдавать смысловое совпадение за точное.
            entries = await self._memory.semantic_search(
                telegram_user_id, query, self._ai_client
            )
            header = f"Точных совпадений с «{query}» нет, но вот похожее:"

        if not entries:
            return f"🤷 Ничего не нашёл про «{query}»."

        lines = [header]
        lines.extend(f"• {entry.content}" for entry in entries[:_MAX_RECALL_RESULTS])
        return "\n".join(lines)

    async def _complete_task(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую задачу отметить выполненной?"
        matches = await self._tasks.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"🤔 Не нашёл активную задачу «{title_query}»."
        task = await self._tasks.complete_task_by_title(telegram_user_id, title_query)
        if task is None:
            return f"🤔 Не нашёл активную задачу «{title_query}»."
        note = _ambiguity_note(matches, title_query)
        recurrence_note = (
            "\n\nСоздал следующую — она повторится автоматически."
            if task.recurrence
            else ""
        )
        return f"✅ «{task.title}» — сделано!{recurrence_note}{note}"

    async def _delete_task(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую задачу удалить?"
        matches = await self._tasks.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"🤔 Не нашёл активную задачу «{title_query}»."
        task = await self._tasks.delete_task_by_title(telegram_user_id, title_query)
        if task is None:
            return f"🤔 Не нашёл активную задачу «{title_query}»."
        note = _ambiguity_note(matches, title_query)
        return f"🗑 Удалил задачу «{task.title}».{note}"

    async def _list_habits(self, telegram_user_id: int) -> str:
        habits = await self._habits.list_active_habits(telegram_user_id)
        if not habits:
            return "Активных привычек нет."
        streaks = await self._habits.get_streaks_bulk(
            telegram_user_id, [h.id for h in habits]
        )
        lines = []
        for index, habit in enumerate(habits, start=1):
            streak = streaks.get(habit.id, 0)
            suffix = f" — 🔥 {streak} дней подряд" if streak > 0 else ""
            lines.append(f"{index}. {habit.title}{suffix}")
        return "\n".join(lines)

    async def _habit_done(self, telegram_user_id: int, title_query: str) -> str:
        if not title_query:
            return "Какую привычку отметить выполненной?"
        matches = await self._habits.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return f"🤔 Не нашёл активную привычку «{title_query}»."
        habit = await self._habits.mark_done_today(telegram_user_id, title_query)
        if habit is None:
            return f"🤔 Не нашёл активную привычку «{title_query}»."
        streak = await self._habits.get_streak(telegram_user_id, habit.id)
        note = _ambiguity_note(matches, title_query)
        # Число серии уже названо строкой выше — юбилей его не повторяет,
        # иначе сообщение выглядит как заевшая пластинка.
        celebration = (
            "\n🎉 Круглая цифра — так держать!" if streak in _STREAK_MILESTONES else ""
        )
        return f"🔥 «{habit.title}» — {streak} дней подряд!{celebration}{note}"

    async def _add_watchlist_item(
        self, telegram_user_id: int, parsed: ParsedIntent
    ) -> EngineResult:
        if not parsed.title:
            return EngineResult("Что посмотреть-то? Например: «посмотреть фильм Дюна».")
        if self._watchlist is None:
            # Сервис не подключён (не должно случаться в проде, см.
            # handlers.py) — не терять сообщение молча, а хотя бы
            # сохранить как задачу.
            text, task = await self._add_task(telegram_user_id, parsed)
            return EngineResult(text, task)

        item = await self._watchlist.create_item(
            telegram_user_id, parsed.title, parsed.media_type or "other"
        )
        emoji = MEDIA_TYPE_EMOJI.get(item.media_type, "🎯")
        return EngineResult(f"{emoji} Добавил в список: «{item.title}»")

    async def _list_watchlist(self, telegram_user_id: int) -> str:
        """Текстовый фолбэк (без кнопок) — обычно перехватывается раньше
        на уровне handlers.py, который вместо этого шлёт интерактивную
        клавиатуру (см. _send_watchlist_keyboard), как и для LIST_HABITS."""
        if self._watchlist is None:
            return "Смотреть/читать пока нечего."
        items = await self._watchlist.list_active_items(telegram_user_id)
        if not items:
            return "Смотреть/читать пока нечего."
        lines = []
        for index, item in enumerate(items, start=1):
            emoji = MEDIA_TYPE_EMOJI.get(item.media_type, "🎯")
            lines.append(f"{index}. {emoji} {item.title}")
        return "\n".join(lines)

    async def _journal_entry(self, telegram_user_id: int, content: str) -> str:
        if not content:
            return "Что записать в дневник? Например: «дневник: продуктивный день»."
        await self._memory.save(
            telegram_user_id, MemoryType.JOURNAL, content, source="telegram"
        )
        return "📝 Записал в дневник."


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
