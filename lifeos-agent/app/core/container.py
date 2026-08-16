"""
Фабрики сборки сервисов — единое место, где собираются composite-объекты,
требующие сразу несколько сервисов (ConversationEngine — 5 штук,
PendingPromptService — 3 штуки).

Раньше эта сборка была продублирована в handlers.py и jobs.py (см.
AUDIT.md, A-3) — правка сигнатуры конструктора требовала находить и
чинить все места вручную. Однострочная сборка одного сервиса
(`TaskService(TaskRepository(session))`) фабрики не заменяют — это не
дублирование, а обычная инстанциация.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.conversation.engine import ConversationEngine
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
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService


def build_task_service(session: AsyncSession) -> TaskService:
    return TaskService(TaskRepository(session))


def build_habit_service(session: AsyncSession) -> HabitService:
    return HabitService(HabitRepository(session))


def build_memory_service(session: AsyncSession) -> MemoryService:
    return MemoryService(MemoryRepository(session))


def build_goal_service(session: AsyncSession) -> GoalService:
    return GoalService(GoalRepository(session))


def build_watchlist_service(session: AsyncSession) -> WatchlistService:
    return WatchlistService(WatchlistRepository(session))


def build_prompt_service(session: AsyncSession) -> PendingPromptService:
    return PendingPromptService(
        PendingPromptRepository(session),
        build_goal_service(session),
        build_habit_service(session),
        build_memory_service(session),
    )


def build_engine(
    session: AsyncSession, ai_client: AIClient | None = None
) -> ConversationEngine:
    return ConversationEngine(
        build_task_service(session),
        build_habit_service(session),
        build_memory_service(session),
        ai_client=ai_client,
        goal_service=build_goal_service(session),
        pending_prompt_service=build_prompt_service(session),
        watchlist_service=build_watchlist_service(session),
    )
