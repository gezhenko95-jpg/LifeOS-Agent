"""
Tasks Service.

Вся бизнес-логика задач находится здесь. Repository — только БД,
API/Conversation — только вызывают этот сервис.
"""

import calendar
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.ownership import owned_or_none
from app.crm.repository import ContactRepository
from app.goals.repository import GoalRepository
from app.habits.repository import HabitRepository
from app.tasks.models import Task, TaskComment
from app.tasks.repository import TaskCommentRepository, TaskRepository

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
    def __init__(
        self,
        repository: TaskRepository,
        contact_repository: Optional[ContactRepository] = None,
        habit_repository: Optional[HabitRepository] = None,
        goal_repository: Optional[GoalRepository] = None,
    ) -> None:
        self._repository = repository
        # Опционально (как ai_client у ConversationEngine) — валидирует
        # владение contact_id, если задан. Старые вызовы TaskService(repo)
        # без него по-прежнему работают, просто без этой проверки
        # (тот же trade-off, что уже принят проектом для A-1, AUDIT.md).
        self._contacts = contact_repository
        # habit_repository — та же опциональная валидация владения, но
        # для habit_id (отчёт владельца 24.08, вечер #6: "привязать
        # привычку" к задаче) — прямая копия приёма с contact_repository.
        self._habits = habit_repository
        # goal_repository — тот же приём для goal_id (живая проверка 25.08:
        # "в цели тоже возможность связывать цель с задачей").
        self._goals = goal_repository

    async def create_task(
        self,
        telegram_user_id: int,
        title: str,
        due_date: Optional[datetime] = None,
        priority: str = "normal",
        recurrence: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
        parent_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        habit_id: Optional[int] = None,
        goal_id: Optional[int] = None,
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
        if contact_id is not None:
            await self._check_contact_owned(telegram_user_id, contact_id)
        if habit_id is not None:
            await self._check_habit_owned(telegram_user_id, habit_id)
        if goal_id is not None:
            await self._check_goal_owned(telegram_user_id, goal_id)

        if parent_id is not None:
            parent = owned_or_none(
                await self._repository.get_by_id(parent_id), telegram_user_id
            )
            if parent is None:
                raise ValueError("Родительская задача не найдена")
            if parent.parent_id is not None:
                # Иерархия плоская — два уровня максимум (эпик → подзадача).
                # Подзадача подзадачи усложнила бы и UI, и рекурсивное
                # каскадное удаление без реальной пользы для одного
                # пользователя (specs/022-tasks-v2.md).
                raise ValueError(
                    "У подзадачи не может быть своих подзадач — "
                    "добавьте её к верхней задаче"
                )

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
            parent_id=parent_id,
            contact_id=contact_id,
            habit_id=habit_id,
            goal_id=goal_id,
        )
        return await self._repository.add(task)

    async def _check_contact_owned(
        self, telegram_user_id: int, contact_id: int
    ) -> None:
        """Пропускается молча, если сервис собран без contact_repository
        (см. __init__) — тот же trade-off, что у A-1 в AUDIT.md."""
        if self._contacts is None:
            return
        contact = owned_or_none(
            await self._contacts.get_by_id(contact_id), telegram_user_id
        )
        if contact is None:
            raise ValueError("Контакт не найден")

    async def _check_habit_owned(self, telegram_user_id: int, habit_id: int) -> None:
        """Пропускается молча, если сервис собран без habit_repository —
        прямая копия _check_contact_owned."""
        if self._habits is None:
            return
        habit = owned_or_none(await self._habits.get_by_id(habit_id), telegram_user_id)
        if habit is None:
            raise ValueError("Привычка не найдена")

    async def _check_goal_owned(self, telegram_user_id: int, goal_id: int) -> None:
        """Пропускается молча, если сервис собран без goal_repository —
        прямая копия _check_habit_owned."""
        if self._goals is None:
            return
        goal = owned_or_none(await self._goals.get_by_id(goal_id), telegram_user_id)
        if goal is None:
            raise ValueError("Цель не найдена")

    async def list_subtasks(self, telegram_user_id: int, parent_id: int) -> list[Task]:
        return await self._repository.list_subtasks(telegram_user_id, parent_id)

    async def list_tasks_for_contact(
        self, telegram_user_id: int, contact_id: int
    ) -> list[Task]:
        """Задачи, привязанные к контакту CRM — обратный просмотр
        Task.contact_id со стороны карточки человека."""
        return await self._repository.list_by_contact(telegram_user_id, contact_id)

    async def count_subtasks_by_parents(
        self, telegram_user_id: int, parent_ids: list[int]
    ) -> dict[int, int]:
        return await self._repository.count_subtasks_by_parents(
            telegram_user_id, parent_ids
        )

    async def toggle_in_progress(
        self, telegram_user_id: int, task_id: int
    ) -> Optional[Task]:
        """Переключить отметку "в работе". Не трогает lifecycle-статус —
        задача остаётся active/completed, чем была."""
        task = owned_or_none(
            await self._repository.get_by_id(task_id), telegram_user_id
        )
        if task is None:
            return None
        task.in_progress = not task.in_progress
        task.in_progress_started_at = (
            datetime.now(timezone.utc) if task.in_progress else None
        )
        return await self._repository.save(task)

    async def list_active_tasks(self, telegram_user_id: int) -> list[Task]:
        tasks = await self._repository.list_by_user(
            telegram_user_id, status=ACTIVE, top_level_only=True
        )
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
        contact_id: Optional[int] = None,
        clear_contact: bool = False,
        habit_id: Optional[int] = None,
        clear_habit: bool = False,
        goal_id: Optional[int] = None,
        clear_goal: bool = False,
    ) -> Optional[Task]:
        if priority is not None and priority not in _PRIORITY_ORDER:
            raise ValueError(f"Неизвестный приоритет: {priority}")
        if recurrence is not None and recurrence not in _RECURRENCE_INTERVALS:
            raise ValueError(f"Неизвестная периодичность: {recurrence}")
        if contact_id is not None:
            await self._check_contact_owned(telegram_user_id, contact_id)
        if habit_id is not None:
            await self._check_habit_owned(telegram_user_id, habit_id)
        if goal_id is not None:
            await self._check_goal_owned(telegram_user_id, goal_id)

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
        if clear_contact:
            task.contact_id = None
        elif contact_id is not None:
            task.contact_id = contact_id
        if clear_habit:
            task.habit_id = None
        elif habit_id is not None:
            task.habit_id = habit_id
        if clear_goal:
            task.goal_id = None
        elif goal_id is not None:
            task.goal_id = goal_id

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


class TaskCommentService:
    """Комментарии к задаче — отдельный сервис (ADR-005), но с проверкой
    владения через TaskRepository: у комментария своя telegram_user_id
    (совпадает с задачей, отдельное поле — на случай будущей
    мультиарендности, см. MULTIUSER.md), но авторитетна принадлежность
    именно ЗАДАЧИ, не комментария."""

    def __init__(
        self, repository: TaskCommentRepository, task_repository: TaskRepository
    ) -> None:
        self._repository = repository
        self._tasks = task_repository

    async def add_comment(
        self, telegram_user_id: int, task_id: int, text: str
    ) -> Optional[TaskComment]:
        text = text.strip()
        if not text:
            raise ValueError("Комментарий не может быть пустым")
        task = owned_or_none(await self._tasks.get_by_id(task_id), telegram_user_id)
        if task is None:
            return None
        comment = TaskComment(
            task_id=task_id, telegram_user_id=telegram_user_id, text=text
        )
        return await self._repository.add(comment)

    async def list_comments(
        self, telegram_user_id: int, task_id: int
    ) -> list[TaskComment]:
        task = owned_or_none(await self._tasks.get_by_id(task_id), telegram_user_id)
        if task is None:
            return []
        return await self._repository.list_by_task(task_id)

    async def count_by_tasks(self, task_ids: list[int]) -> dict[int, int]:
        return await self._repository.count_by_tasks(task_ids)

    async def delete_comment(
        self, telegram_user_id: int, comment_id: int
    ) -> Optional[TaskComment]:
        comment = await self._repository.get_by_id(comment_id)
        if comment is None:
            return None
        task = owned_or_none(
            await self._tasks.get_by_id(comment.task_id), telegram_user_id
        )
        if task is None:
            return None
        await self._repository.delete(comment)
        return comment
