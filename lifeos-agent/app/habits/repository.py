"""
Репозиторий для привычек и их логов.

Единственное место, где выполняются SQL-запросы к таблицам `habits` и
`habit_logs`. Никакой бизнес-логики (расчёт стрика — в service.py).
"""

from collections import defaultdict
from datetime import date, time

from sqlalchemy import func, or_, select

from app.core.repository import BaseRepository, escape_like
from app.habits.models import Habit, HabitLog, HabitStreakFreeze


class HabitRepository(BaseRepository[Habit]):
    model = Habit

    async def list_by_user(
        self, telegram_user_id: int, include_archived: bool = False
    ) -> list[Habit]:
        query = select(Habit).where(Habit.telegram_user_id == telegram_user_id)
        if not include_archived:
            query = query.where(Habit.archived.is_(False))
        query = query.order_by(Habit.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def find_active_by_title(
        self, telegram_user_id: int, needle: str
    ) -> list[Habit]:
        """Активные привычки, чьё название содержит needle — фильтр в БД
        (см. AUDIT.md, P-2), а не "загрузить все и отфильтровать в
        Python"."""
        query = select(Habit).where(
            Habit.telegram_user_id == telegram_user_id,
            Habit.archived.is_(False),
            Habit.title.ilike(f"%{escape_like(needle)}%", escape="\\"),
        )
        query = query.order_by(Habit.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_due_reminders(self, now: time, today: date) -> list[Habit]:
        """Привычки, которым пора напомнить: время напоминания уже
        наступило, а сегодня о них ещё не напоминали.

        Через всех пользователей — проект пока single-user, тот же приём,
        что у `TaskRepository.list_due_unreminded` (см. также
        MULTIUSER.md: при мультиарендности здесь появится фильтр по
        активным пользователям, а не по владельцу из настроек).

        «Уже отмечена сегодня» здесь НЕ проверяется: это условие живёт в
        сервисе, где и так загружаются логи (иначе join ради того, что
        дешевле проверить на горстке привычек)."""
        query = select(Habit).where(
            Habit.archived.is_(False),
            Habit.reminder_time.is_not(None),
            Habit.reminder_time <= now,
            or_(Habit.last_reminded_on.is_(None), Habit.last_reminded_on < today),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def has_log_on(self, habit_id: int, day: date) -> bool:
        query = select(HabitLog).where(
            HabitLog.habit_id == habit_id, HabitLog.completed_on == day
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def add_log(self, habit_id: int, day: date) -> HabitLog:
        log = HabitLog(habit_id=habit_id, completed_on=day)
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def list_logs(self, habit_id: int) -> list[HabitLog]:
        query = (
            select(HabitLog)
            .where(HabitLog.habit_id == habit_id)
            .order_by(HabitLog.completed_on.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_logs_for_habits(
        self, habit_ids: list[int]
    ) -> dict[int, list[HabitLog]]:
        """Логи сразу для нескольких привычек, одним запросом.

        Экран со списком привычек (или брифинг/дайджест) считает стрик
        КАЖДОЙ привычки — без этого метода list_logs вызывался бы в
        цикле, по одному запросу на привычку (см. AUDIT.md, P-1). Пустой
        список на входе — пустой словарь: WHERE habit_id IN () в
        SQLAlchemy валиден, но экономим один поход к БД впустую.
        """
        if not habit_ids:
            return {}

        query = select(HabitLog).where(HabitLog.habit_id.in_(habit_ids))
        result = await self._session.execute(query)

        grouped: dict[int, list[HabitLog]] = defaultdict(list)
        for log in result.scalars():
            grouped[log.habit_id].append(log)
        return dict(grouped)

    # --- Стрик-заморозка (specs/029) --------------------------------

    async def add_streak_freeze(self, habit_id: int, day: date) -> HabitStreakFreeze:
        freeze = HabitStreakFreeze(habit_id=habit_id, protected_on=day)
        self._session.add(freeze)
        await self._session.commit()
        await self._session.refresh(freeze)
        return freeze

    async def list_freeze_days_for_habits(
        self, habit_ids: list[int]
    ) -> dict[int, set[date]]:
        """Замороженные дни сразу для нескольких привычек, одним
        запросом (тот же довод, что у list_logs_for_habits — списки/
        брифинг не должны ходить в БД в цикле, см. AUDIT.md, P-1)."""
        if not habit_ids:
            return {}

        query = select(
            HabitStreakFreeze.habit_id, HabitStreakFreeze.protected_on
        ).where(HabitStreakFreeze.habit_id.in_(habit_ids))
        result = await self._session.execute(query)

        grouped: dict[int, set[date]] = defaultdict(set)
        for habit_id, protected_on in result.all():
            grouped[habit_id].add(protected_on)
        return dict(grouped)

    async def count_used_freezes(self, telegram_user_id: int) -> int:
        """Сколько заморозок уже потрачено всего — через JOIN на Habit,
        владение у HabitStreakFreeze своего telegram_user_id нет (см.
        докстринг модели)."""
        query = (
            select(func.count())
            .select_from(HabitStreakFreeze)
            .join(Habit, Habit.id == HabitStreakFreeze.habit_id)
            .where(Habit.telegram_user_id == telegram_user_id)
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())
