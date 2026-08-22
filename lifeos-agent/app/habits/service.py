"""
Habits Service.

Вся бизнес-логика привычек находится здесь. Repository — только БД,
API/Conversation — только вызывают этот сервис. См. specs/004-habits.md.

Расчёт стрика (по датам) — в app/habits/streaks.py, чистые функции без
БД. Здесь только загрузка логов и раскладка в set[date]. Одиночные
методы (get_streak и т.д.) остаются для мест, где нужна ОДНА привычка
(например, сразу после mark_done); там, где привычек несколько (списки,
брифинг, дайджест, инсайты), используйте *_bulk — иначе получится N+1
запрос, по одному на привычку (см. AUDIT.md, P-1).
"""

from datetime import date, datetime, time
from typing import Optional

from app.core.ownership import owned_or_none
from app.habits.models import Habit
from app.habits.repository import HabitRepository
from app.habits.streaks import current_streak, days_since_last, longest_streak
from app.habits.templates import HabitTemplate


class HabitService:
    def __init__(self, repository: HabitRepository) -> None:
        self._repository = repository

    async def create_habit(
        self,
        telegram_user_id: int,
        title: str,
        description: Optional[str] = None,
        reminder_time: Optional[time] = None,
    ) -> Habit:
        title = title.strip()
        if not title:
            raise ValueError("Название привычки не может быть пустым")

        habit = Habit(
            telegram_user_id=telegram_user_id,
            title=title,
            description=(description or "").strip() or None,
            reminder_time=reminder_time,
        )
        return await self._repository.add(habit)

    async def create_from_template(
        self, telegram_user_id: int, template: HabitTemplate
    ) -> Habit:
        """Готовая привычка из каталога (см. app/habits/templates.py) —
        с описанием и временем напоминания, проставленными заранее."""
        return await self.create_habit(
            telegram_user_id,
            template.title,
            template.description,
            template.reminder_time,
        )

    async def update_habit(
        self,
        telegram_user_id: int,
        habit_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reminder_time: Optional[time] = None,
        clear_reminder: bool = False,
        clear_description: bool = False,
    ) -> Optional[Habit]:
        """Правка привычки. None — не найдена или чужая.

        `None` в поле означает «не трогать», а не «очистить» — иначе
        нельзя было бы поменять одно название, не сбив напоминание. Для
        снятия напоминания/описания есть явные `clear_*`: два разных
        намерения не должны выражаться одним и тем же `None`."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None

        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("Название привычки не может быть пустым")
            habit.title = title

        if clear_description:
            habit.description = None
        elif description is not None:
            habit.description = description.strip() or None

        if clear_reminder:
            habit.reminder_time = None
            # Иначе снятое и заново выставленное в тот же день
            # напоминание не сработало бы до завтра.
            habit.last_reminded_on = None
        elif reminder_time is not None:
            habit.reminder_time = reminder_time
            habit.last_reminded_on = None

        return await self._repository.save(habit)

    async def list_active_habits(self, telegram_user_id: int) -> list[Habit]:
        return await self._repository.list_by_user(telegram_user_id)

    async def find_active_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> list[Habit]:
        """Найти активные привычки пользователя по подстроке названия.

        Фильтрация — в БД (см. app/habits/repository.py, AUDIT.md P-2)."""
        query = title_query.strip()
        return await self._repository.find_active_by_title(telegram_user_id, query)

    async def mark_done_today(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Habit]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        return await self._mark_done(matches[0])

    async def mark_done_by_id(
        self, telegram_user_id: int, habit_id: int
    ) -> Optional[Habit]:
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None
        return await self._mark_done(habit)

    async def _mark_done(self, habit: Habit) -> Habit:
        today = date.today()
        already_done = await self._repository.has_log_on(habit.id, today)
        if not already_done:
            await self._repository.add_log(habit.id, today)
        return habit

    async def _completed_days(self, habit_id: int) -> set[date]:
        logs = await self._repository.list_logs(habit_id)
        return {log.completed_on for log in logs}

    async def _owned_ids(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> list[int]:
        """Пересечь запрошенные id с привычками, реально принадлежащими
        пользователю — один запрос, а не get_by_id в цикле (иначе
        регрессия N+1, см. AUDIT.md, P-1)."""
        owned = await self._repository.list_by_user(
            telegram_user_id, include_archived=True
        )
        owned_ids = {habit.id for habit in owned}
        return [habit_id for habit_id in habit_ids if habit_id in owned_ids]

    async def get_streak(self, telegram_user_id: int, habit_id: int) -> int:
        """Одна привычка — см. get_streaks_bulk для списка."""
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return 0
        return current_streak(await self._completed_days(habit_id))

    async def get_streaks_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, int]:
        """Текущий стрик для нескольких привычек одним запросом к БД
        (см. AUDIT.md, P-1). Привычка без единого лога — 0, как и у
        одиночного get_streak."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: current_streak(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def days_since_last_completion_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, Optional[int]]:
        """Сколько дней прошло с последней отметки, для нескольких
        привычек одним запросом (см. AUDIT.md, P-1) — нэджи проверяют
        это условие для каждой активной привычки. None — ни разу не
        отмечалась. Одиночного варианта нет: единственный вызывающий
        код (nudges.py) всегда работает списком активных привычек."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: days_since_last(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def get_longest_streaks_bulk(
        self, telegram_user_id: int, habit_ids: list[int]
    ) -> dict[int, int]:
        """Рекорд серии для нескольких привычек одним запросом — для
        Personal Insights (см. app/insights/service.py, AUDIT.md P-1)."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: longest_streak(
                {log.completed_on for log in by_habit.get(habit_id, [])}
            )
            for habit_id in owned_ids
        }

    async def get_completed_days_bulk(
        self, telegram_user_id: int, habit_ids: list[int], since: date
    ) -> dict[int, set[date]]:
        """Дни (>= since), когда привычка была отмечена, для нескольких
        привычек одним запросом (см. AUDIT.md, P-1) — используется
        графиком дайджеста и вечерним чек-ином, где привычки
        перебираются циклом. Одиночного варианта нет: оба вызывающих
        места всегда работают списком привычек."""
        owned_ids = await self._owned_ids(telegram_user_id, habit_ids)
        by_habit = await self._repository.list_logs_for_habits(owned_ids)
        return {
            habit_id: {
                log.completed_on
                for log in by_habit.get(habit_id, [])
                if log.completed_on >= since
            }
            for habit_id in owned_ids
        }

    async def list_due_reminders(
        self, now: Optional[time] = None, today: Optional[date] = None
    ) -> list[Habit]:
        """Привычки, о которых пора напомнить прямо сейчас: время
        наступило, сегодня ещё не напоминали И сегодня ещё не отмечена —
        напоминать о том, что человек уже сделал, значит обесценить сами
        напоминания.

        Отметку «напомнили» ставит вызывающий код (`mark_reminded`)
        после фактической отправки: если бот упал между выборкой и
        отправкой, напоминание не потеряется, а придёт следующим
        прогоном."""
        now = now or datetime.now().time()
        today = today or date.today()

        due = await self._repository.list_due_reminders(now, today)
        if not due:
            return []

        done_today = await self._repository.list_logs_for_habits([h.id for h in due])
        return [
            habit
            for habit in due
            if today not in {log.completed_on for log in done_today.get(habit.id, [])}
        ]

    async def mark_reminded(self, habit: Habit, today: Optional[date] = None) -> Habit:
        habit.last_reminded_on = today or date.today()
        return await self._repository.save(habit)

    async def delete_habit(
        self, telegram_user_id: int, habit_id: int
    ) -> Optional[Habit]:
        habit = owned_or_none(
            await self._repository.get_by_id(habit_id), telegram_user_id
        )
        if habit is None:
            return None
        await self._repository.delete(habit)
        return habit
