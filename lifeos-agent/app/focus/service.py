"""
FocusSessionService — вся бизнес-логика фокус-сессий (specs/026).
Repository — только БД, API/бот — только вызывают этот сервис.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.focus.models import CANCELLED, COMPLETED, IN_PROGRESS, ON_BREAK, FocusSession
from app.focus.repository import FocusSessionRepository
from app.habits.streaks import current_streak
from app.shop.models import FOCUS_REWARD
from app.shop.repository import ShopRepository

DEFAULT_WORK_MINUTES = 25
DEFAULT_BREAK_MINUTES = 5

# Награда за завершённую сессию (specs/029, по мотивам Forest/TickTick) —
# сознательно скромнее чек-ина (10-70 монет): фокус-сессии не должны
# конкурировать с основным циклом наград, только слегка его подпитывать.
FOCUS_REWARD_BASE_COINS = 5
# Сессии короче этого порога не награждаются — иначе дробление на мелкие
# сессии было бы выгоднее одной длинной (тот же довод, что критика
# Todoist Karma в исследовании конкурентов, specs/029).
FOCUS_REWARD_MIN_WORK_MINUTES = 15
FOCUS_REWARD_STREAK_BONUS_PER_DAY = 2
FOCUS_REWARD_STREAK_BONUS_CAP_DAYS = 5


class FocusSessionService:
    def __init__(
        self,
        repository: FocusSessionRepository,
        shop_repository: Optional[ShopRepository] = None,
    ) -> None:
        self._repository = repository
        # Опционально (тот же приём, что payment_repository у
        # DebtService) — без него сессии завершаются точно как раньше,
        # просто без начисления монет. Существующие вызовы
        # FocusSessionService(repository) не ломаются.
        self._shop = shop_repository

    async def start_session(
        self,
        telegram_user_id: int,
        work_minutes: int = DEFAULT_WORK_MINUTES,
        break_minutes: int = DEFAULT_BREAK_MINUTES,
        task_id: Optional[int] = None,
    ) -> FocusSession:
        if work_minutes <= 0 or break_minutes <= 0:
            raise ValueError("Длительность должна быть положительной")
        existing = await self._repository.get_active(telegram_user_id)
        if existing is not None:
            # Pomodoro по смыслу однопоточный — параллельные сессии не
            # имеют смысла (specs/026-focus-sessions.md).
            raise ValueError("Сессия уже идёт — сначала завершите или прервите её")

        now = datetime.now(timezone.utc)
        session = FocusSession(
            telegram_user_id=telegram_user_id,
            task_id=task_id,
            work_minutes=work_minutes,
            break_minutes=break_minutes,
            started_at=now,
            work_ends_at=now + timedelta(minutes=work_minutes),
            status=IN_PROGRESS,
        )
        return await self._repository.add(session)

    async def get_active_session(self, telegram_user_id: int) -> Optional[FocusSession]:
        return await self._repository.get_active(telegram_user_id)

    async def cancel_session(
        self, telegram_user_id: int, session_id: int
    ) -> Optional[FocusSession]:
        session = owned_or_none(
            await self._repository.get_by_id(session_id), telegram_user_id
        )
        if session is None or session.status not in (IN_PROGRESS, ON_BREAK):
            return None
        session.status = CANCELLED
        return await self._repository.save(session)

    async def stats_since(
        self, telegram_user_id: int, since: datetime
    ) -> tuple[int, int]:
        """(число завершённых сессий, суммарные минуты) — для /ui и
        еженедельного дайджеста."""
        return await self._repository.stats_since(telegram_user_id, since)

    # --- Опрашивающая джоба (app/telegram/jobs.py::send_focus_notifications_job) ---

    async def list_due_work_end(
        self, now: Optional[datetime] = None
    ) -> list[FocusSession]:
        return await self._repository.list_due_work_end(
            now or datetime.now(timezone.utc)
        )

    async def list_due_break_end(
        self, now: Optional[datetime] = None
    ) -> list[FocusSession]:
        return await self._repository.list_due_break_end(
            now or datetime.now(timezone.utc)
        )

    async def mark_work_notified(self, session: FocusSession) -> FocusSession:
        """Работа закончилась → перерыв. break_ends_at считается от
        work_ends_at (запланированного момента), а не от "сейчас" —
        иначе задержка опроса накапливалась бы в каждом следующем
        переходе (тот же довод, что у _maybe_create_next_occurrence
        в TaskService: серия не должна "плыть")."""
        now = datetime.now(timezone.utc)
        session.status = ON_BREAK
        session.work_notified_at = now
        session.break_ends_at = session.work_ends_at + timedelta(
            minutes=session.break_minutes
        )
        return await self._repository.save(session)

    async def mark_break_notified(self, session: FocusSession) -> FocusSession:
        now = datetime.now(timezone.utc)
        # Считаем награду ДО мутации/save (см. инвариант BaseRepository:
        # мутация и save должны идти подряд без await между ними) — сам
        # запрос за наградой read-only, ничего в session не трогает.
        reward = await self._reward_for_completion(session, now.date())
        session.status = COMPLETED
        session.break_notified_at = now
        saved = await self._repository.save(session)
        if reward > 0:
            await self._shop.add_transaction(
                telegram_user_id=session.telegram_user_id,
                amount=reward,
                reason=FOCUS_REWARD,
            )
        # Не колонка модели, не персистится — только чтобы вызывающий код
        # (телеграм-уведомление в jobs.py) знал сумму, не делая для этого
        # отдельный запрос.
        saved.reward_coins = reward
        return saved

    async def _reward_for_completion(self, session: FocusSession, today: date) -> int:
        if self._shop is None or session.work_minutes < FOCUS_REWARD_MIN_WORK_MINUTES:
            return 0

        days_before = await self._repository.list_completed_days(
            session.telegram_user_id
        )
        reward = FOCUS_REWARD_BASE_COINS
        if today not in days_before:
            # Первая завершённая сессия сегодня — продлевает "фокус-
            # стрик", вторая-третья в тот же день бонуса уже не даёт
            # (иначе выгоднее дробить одну сессию на несколько мелких).
            streak = current_streak(days_before | {today}, today)
            reward += FOCUS_REWARD_STREAK_BONUS_PER_DAY * min(
                streak, FOCUS_REWARD_STREAK_BONUS_CAP_DAYS
            )
        return reward
