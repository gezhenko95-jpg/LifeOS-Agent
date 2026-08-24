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
from app.assistant.repository import AssistantRepository
from app.assistant.service import AssistantService
from app.conversation.engine import ConversationEngine
from app.crm.repository import ContactCommentRepository, ContactRepository
from app.crm.service import ContactCommentService, ContactService
from app.digest.repository import DigestRepository
from app.digest.scraper import get_channel_scraper
from app.digest.service import DigestService
from app.finance.repository import DebtRepository, FinanceRepository
from app.finance.service import DebtService, FinanceService
from app.focus.repository import FocusSessionRepository
from app.focus.service import FocusSessionService
from app.goals.repository import GoalRepository
from app.goals.service import GoalService
from app.habits.repository import HabitRepository
from app.habits.service import HabitService
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.mood.repository import MoodRepository
from app.mood.service import MoodService
from app.proactive.repository import PendingPromptRepository
from app.proactive.service import PendingPromptService
from app.rewards.repository import RewardsRepository
from app.rewards.service import RewardsService
from app.tasks.repository import TaskCommentRepository, TaskRepository
from app.tasks.service import TaskCommentService, TaskService
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService


def build_task_service(session: AsyncSession) -> TaskService:
    # contact_repository/habit_repository — валидируют владение contact_id/
    # habit_id при связке задачи с человеком/привычкой (specs/022-tasks-v2.md,
    # отчёт владельца 24.08 вечер #6). Прямая сборка
    # TaskService(TaskRepository(session)) в нескольких местах jobs.py/
    # handlers.py/callbacks.py (A-3, ещё не отрефакторено) этой проверки
    # не получает — существующий, не новый trade-off.
    return TaskService(
        TaskRepository(session), ContactRepository(session), HabitRepository(session)
    )


def build_task_comment_service(session: AsyncSession) -> TaskCommentService:
    return TaskCommentService(TaskCommentRepository(session), TaskRepository(session))


def build_habit_service(session: AsyncSession) -> HabitService:
    return HabitService(HabitRepository(session))


def build_memory_service(session: AsyncSession) -> MemoryService:
    return MemoryService(MemoryRepository(session))


def build_goal_service(session: AsyncSession) -> GoalService:
    return GoalService(GoalRepository(session))


def build_watchlist_service(session: AsyncSession) -> WatchlistService:
    return WatchlistService(WatchlistRepository(session))


def build_rewards_service(session: AsyncSession) -> RewardsService:
    return RewardsService(RewardsRepository(session))


def build_finance_service(session: AsyncSession) -> FinanceService:
    return FinanceService(FinanceRepository(session))


def build_debt_service(session: AsyncSession) -> DebtService:
    return DebtService(DebtRepository(session))


def build_focus_service(session: AsyncSession) -> FocusSessionService:
    return FocusSessionService(FocusSessionRepository(session))


def build_contact_service(session: AsyncSession) -> ContactService:
    return ContactService(ContactRepository(session))


def build_contact_comment_service(session: AsyncSession) -> ContactCommentService:
    return ContactCommentService(
        ContactCommentRepository(session), ContactRepository(session)
    )


def build_mood_service(session: AsyncSession) -> MoodService:
    return MoodService(MoodRepository(session))


def build_assistant_service(session: AsyncSession) -> AssistantService:
    return AssistantService(AssistantRepository(session))


def build_digest_service(session: AsyncSession) -> DigestService:
    """Скрейпер отдаётся фабрикой, а не создаётся здесь: внутри — один
    httpx.AsyncClient на процесс (keep-alive, см. app/digest/scraper.py),
    новый на каждое сообщение обнулил бы весь его смысл."""
    return DigestService(DigestRepository(session), get_channel_scraper())


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
        rewards_service=build_rewards_service(session),
        finance_service=build_finance_service(session),
        assistant_service=build_assistant_service(session),
    )
