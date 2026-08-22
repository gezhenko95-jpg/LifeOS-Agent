"""
Tasks Service.

Вся бизнес-логика задач находится здесь. Repository — только БД,
API/Conversation — только вызывают этот сервис.
"""

import calendar
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.tasks.models import Task
from app.tasks.repository import TaskRepository

ACTIVE = "active"
# Палитра меток календаря. Имена, а не HEX: цвета берутся из
# переменных темы, поэтому «red» переживает смену оформления, а
# конкретный код цвета — нет. Пустая строка снимает метку.
TASK_COLORS = {"red", "orange", "green", "blue", "violet"}

COMPLETED = "completed"

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
_RECURRENCE_INTERVALS = {"daily", "weekly", "monthly"}


def _advance_date(due_date: datetime, recurrence: str) -> datetime:
    if recurrence == "daily":
        return due_date + timedelta(days=1)
    if recurrence == "weekly":
        return due_date + timedelta(days=7)
    if recurrence == "monthly":
        return _add_month(due_date)
    raise ValueError(f"Неизвестная периодичность: {recurrence}")


def _add_month(dt: datetime) -> datetime:
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day_of_target_month = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day_of_target_month)
    return dt.replace(year=year, month=month, day=day)


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    async def create_task(
        self,
        telegram_user_id: int,
        title: str,
        due_date: Optional[datetime] = None,
        priority: str = "normal",
        recurrence: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Название задачи не может быть пустым")
        if priority not in _PRIORITY_ORDER:
            raise ValueError(f"Неизвестный приоритет: {priority}")
        if color and color.strip().lower() not in TASK_COLORS:
            raise ValueError(f"Неизвестный цвет: {color}")
        if recurrence is not None and recurrence not in _RECURRENCE_INTERVALS:
            raise ValueError(f"Неизвестная периодичность: {recurrence}")

        if recurrence is not None and due_date is None:
            # "каждый день"/"каждый месяц" без конкретной даты (в отличие
            # от "каждый понедельник", где день уже определён парсером) —
            # стартуем с ближайшего повторения, а не оставляем без даты,
            # иначе повторяющаяся задача никогда не наступит.
            due_date = _advance_date(datetime.now(timezone.utc), recurrence)

        task = Task(
            telegram_user_id=telegram_user_id,
            title=title,
            due_date=due_date,
            status=ACTIVE,
            priority=priority,
            recurrence=recurrence,
            description=(description or "").strip() or None,
            color=(color or "").strip().lower() or None,
        )
        return await self._repository.add(task)

    async def list_active_tasks(self, telegram_user_id: int) -> list[Task]:
        tasks = await self._repository.list_by_user(telegram_user_id, status=ACTIVE)
        tasks.sort(key=lambda task: _PRIORITY_ORDER.get(task.priority, 1))
        return tasks

    async def update_task(
        self,
        telegram_user_id: int,
        task_id: int,
        title: Optional[str] = None,
        due_date: Optional[datetime] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        recurrence: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Optional[Task]:
        if priority is not None and priority not in _PRIORITY_ORDER:
            raise ValueError(f"Неизвестный приоритет: {priority}")
        if recurrence is not None and recurrence not in _RECURRENCE_INTERVALS:
            raise ValueError(f"Неизвестная периодичность: {recurrence}")

        task = owned_or_none(
            await self._repository.get_by_id(task_id), telegram_user_id
        )
        if task is None:
            return None

        was_active = task.status == ACTIVE
        if title is not None:
            task.title = title
        if due_date is not None:
            task.due_date = due_date
        if status is not None:
            task.status = status
            if status == COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
        if priority is not None:
            task.priority = priority
        if recurrence is not None:
            task.recurrence = recurrence
        if description is not None:
            # Пустая строка стирает описание — отдельный флаг не нужен,
            # описание ничем больше не управляет (в отличие от времени
            # напоминания у привычки, см. HabitService.update_habit).
            task.description = description.strip() or None
        if color is not None:
            color = color.strip().lower()
            if color and color not in TASK_COLORS:
                raise ValueError(f"Неизвестный цвет: {color}")
            task.color = color or None

        saved = await self._repository.save(task)
        if was_active and status == COMPLETED:
            await self._maybe_create_next_occurrence(saved)
        return saved

    async def delete_task(self, telegram_user_id: int, task_id: int) -> Optional[Task]:
        task = owned_or_none(
            await self._repository.get_by_id(task_id), telegram_user_id
        )
        if task is None:
            return None
        await self._repository.delete(task)
        return task

    async def find_active_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> list[Task]:
        """Найти активные задачи пользователя по подстроке названия.

        Сама фильтрация — в БД (см. app/tasks/repository.py, AUDIT.md
        P-2); здесь только приоритетная сортировка поверх уже небольшого
        набора совпадений, как у list_active_tasks."""
        query = title_query.strip()
        matches = await self._repository.find_active_by_title(telegram_user_id, query)
        matches.sort(key=lambda task: _PRIORITY_ORDER.get(task.priority, 1))
        return matches

    async def complete_task_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Task]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        task = matches[0]
        task.status = COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        saved = await self._repository.save(task)
        await self._maybe_create_next_occurrence(saved)
        return saved

    async def _maybe_create_next_occurrence(self, task: Task) -> None:
        """Если задача повторяющаяся — создать следующее вхождение с
        датой, отсчитанной от ИСХОДНОГО due_date (а не от даты
        завершения) — так серия не "плывёт", если задачу отметили
        выполненной с опозданием."""
        if not task.recurrence or task.due_date is None:
            return
        next_task = Task(
            telegram_user_id=task.telegram_user_id,
            title=task.title,
            due_date=_advance_date(task.due_date, task.recurrence),
            status=ACTIVE,
            priority=task.priority,
            recurrence=task.recurrence,
        )
        await self._repository.add(next_task)

    async def delete_task_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Task]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        task = matches[0]
        await self._repository.delete(task)
        return task

    async def list_due_reminders(self) -> list[Task]:
        """Активные задачи с наступившим сроком, по которым ещё не напомнили.

        Без фильтра по telegram_user_id — проект single-user (PROJECT.md),
        как и у build_morning_briefing.
        """
        return await self._repository.list_due_unreminded(datetime.now(timezone.utc))

    async def mark_reminded(
        self, telegram_user_id: int, task_id: int
    ) -> Optional[Task]:
        task = owned_or_none(
            await self._repository.get_by_id(task_id), telegram_user_id
        )
        if task is None:
            return None
        task.reminded_at = datetime.now(timezone.utc)
        return await self._repository.save(task)

    async def count_tasks_completed_since(
        self, telegram_user_id: int, since: datetime
    ) -> int:
        """Сколько задач завершено с момента `since` — для еженедельного
        дайджеста (см. app/scheduler/weekly_digest.py)."""
        return await self._repository.count_completed_since(telegram_user_id, since)

    async def count_tasks_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> int:
        """Сколько задач завершено в [since, until) — для графика по
        неделям (см. app/scheduler/charts.py)."""
        return await self._repository.count_completed_between(
            telegram_user_id, since, until
        )

    async def list_tasks_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> list[Task]:
        """Завершённые в [since, until) задачи целиком (не только счётчик) —
        для Personal Insights (см. app/insights/service.py)."""
        return await self._repository.list_completed_between(
            telegram_user_id, since, until
        )
