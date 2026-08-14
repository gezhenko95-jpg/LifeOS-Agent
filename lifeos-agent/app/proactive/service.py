"""
PendingPromptService — выбор следующего проактивного вопроса и хранение
состояния "открытый вопрос, ждущий ответа" (см.
specs/006-proactive-engagement.md).

Выбор категории — простой детерминированный gap-detection (ADR-004: не
нужен AI там, где хватает обычного кода): спрашиваем про то, чего у
пользователя ещё нет. Примерно в половине случаев (`_with_musing`) к
основному вопросу добавляется вторая строка — экзистенциальный вопрос
или интересный факт-вопрос (`questions.py::MUSING_QUESTIONS`), для
разнообразия. Musing не сохраняется в `pending_prompts` и не участвует в
разборе ответа — это только украшение отправляемого текста.
"""

import random

from app.goals.service import GoalService
from app.habits.service import HabitService
from app.memory.models import MemoryType
from app.memory.service import MemoryService
from app.proactive.models import PendingPrompt
from app.proactive.questions import (
    _MIN_PREFERENCES,
    _MUSING_CHANCE,
    DREAM_QUESTIONS,
    GOAL_QUESTIONS,
    HABIT_QUESTIONS,
    MUSING_QUESTIONS,
    PREFERENCE_QUESTIONS,
    PROJECT_QUESTIONS,
    REFLECT_QUESTIONS,
)
from app.proactive.repository import PendingPromptRepository

# Утренний слот 10:30 (см. pick_morning_reflection): доля дневникового
# вопроса про сон против обычного gap-вопроса о профиле.
_MORNING_JOURNAL_CHANCE = 0.7


class PendingPromptService:
    def __init__(
        self,
        repository: PendingPromptRepository,
        goal_service: GoalService,
        habit_service: HabitService,
        memory_service: MemoryService,
    ) -> None:
        self._repository = repository
        self._goals = goal_service
        self._habits = habit_service
        self._memory = memory_service

    async def pick_and_open(self, telegram_user_id: int) -> str:
        category, question_text = await self._pick_question(telegram_user_id)
        # В pending_prompts уходит ЧИСТЫЙ вопрос (без musing) — именно он
        # даёт AI контекст при разборе ответа (ai_extract.py). Musing —
        # только украшение отправляемого сообщения, к разбору ответа
        # отношения не имеет: если пользователь ответит именно на него,
        # extract_prompt_answer справедливо сочтёт это "unrelated" к
        # основной категории и сообщение уйдёт по обычному пути (см.
        # specs/006-proactive-engagement.md).
        await self._repository.upsert(telegram_user_id, category, question_text)
        return _with_musing(question_text)

    async def pick_morning_reflection(
        self, telegram_user_id: int, allow_gap: bool = True
    ) -> str:
        """Утренний слот 10:30 (см. flows/009-daily-rhythm.md): ~70% —
        дневниковый вопрос про сон (category="journal", ответ ловится без
        AI — ConversationEngine._try_capture_journal), иначе — обычный
        gap-вопрос о профиле, но только если гэп реально есть.
        "reflect" от _pick_question как раз и значит "гэпа нет" — в этом
        случае тоже отдаём дневниковый вопрос, гэпить нечего.

        `allow_gap=False` (передаётся из jobs.py, когда openrouter_api_key
        не задан) полностью отключает gap-ветку: без AI ответ на неё
        всё равно не поймается (ConversationEngine требует ai_client для
        _try_answer_pending_prompt) — открывать неотвечаемый вопрос
        бессмысленно, дневниковая ветка не зависит от AI и работает
        всегда.
        """
        if allow_gap and random.random() >= _MORNING_JOURNAL_CHANCE:
            category, question_text = await self._pick_question(telegram_user_id)
            if category != "reflect":
                await self._repository.upsert(telegram_user_id, category, question_text)
                return _with_musing(question_text)

        question = random.choice(DREAM_QUESTIONS)
        await self._repository.upsert(telegram_user_id, "journal", question)
        return question

    async def pick_gap_question_if_any(self, telegram_user_id: int) -> str | None:
        """Gap-вопрос про цель/привычку/проект/предпочтение, если гэп
        реально есть — иначе None ("reflect" от _pick_question — сигнал
        "гэпа нет", вызывающий код сам решает, что делать при пустоте).
        Используется вечерним итоговым слотом 19:00 (см.
        flows/009-daily-rhythm.md) — там вопрос необязательное дополнение
        к итогам дня, а не главное содержание сообщения."""
        category, question_text = await self._pick_question(telegram_user_id)
        if category == "reflect":
            return None
        await self._repository.upsert(telegram_user_id, category, question_text)
        return question_text

    async def get_open(self, telegram_user_id: int) -> PendingPrompt | None:
        return await self._repository.get_for_user(telegram_user_id)

    async def clear(self, telegram_user_id: int) -> None:
        await self._repository.clear_for_user(telegram_user_id)

    async def _pick_question(self, telegram_user_id: int) -> tuple[str, str]:
        goals = await self._goals.list_active_goals(telegram_user_id)
        if not goals:
            return "goal", random.choice(GOAL_QUESTIONS)

        habits = await self._habits.list_active_habits(telegram_user_id)
        if not habits:
            return "habit", random.choice(HABIT_QUESTIONS)

        projects = await self._memory.list_entries(
            telegram_user_id, type=MemoryType.PROJECT
        )
        if not projects:
            return "project", random.choice(PROJECT_QUESTIONS)

        preferences = await self._memory.list_entries(
            telegram_user_id, type=MemoryType.PREFERENCE
        )
        if len(preferences) < _MIN_PREFERENCES:
            return "preference", random.choice(PREFERENCE_QUESTIONS)

        return "reflect", random.choice(REFLECT_QUESTIONS)


def _with_musing(question_text: str) -> str:
    if random.random() >= _MUSING_CHANCE:
        return question_text
    return f"{question_text}\n\n🤔 {random.choice(MUSING_QUESTIONS)}"
