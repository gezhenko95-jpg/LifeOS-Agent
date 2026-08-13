"""
Tasks Service.

Вся бизнес-логика задач находится здесь. Repository — только БД,
API/Conversation — только вызывают этот сервис.
"""

from datetime import datetime, timezone
from typing import Optional

from app.tasks.models import Task
from app.tasks.repository import TaskRepository

ACTIVE = "active"
COMPLETED = "completed"

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    async def create_task(
        self,
        telegram_user_id: int,
        title: str,
        due_date: Optional[datetime] = None,
        priority: str = "normal",
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Название задачи не может быть пустым")
        if priority not in _PRIORITY_ORDER:
            raise ValueError(f"Неизвестный приоритет: {priority}")

        task = Task(
            telegram_user_id=telegram_user_id,
            title=title,
            due_date=due_date,
            status=ACTIVE,
            priority=priority,
        )
        return await self._repository.add(task)

    async def list_active_tasks(self, telegram_user_id: int) -> list[Task]:
        tasks = await self._repository.list_by_user(telegram_user_id, status=ACTIVE)
        tasks.sort(key=lambda task: _PRIORITY_ORDER.get(task.priority, 1))
        return tasks

    async def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        due_date: Optional[datetime] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Optional[Task]:
        if priority is not None and priority not in _PRIORITY_ORDER:
            raise ValueError(f"Неизвестный приоритет: {priority}")

        task = await self._repository.get_by_id(task_id)
        if task is None:
            return None
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
        return await self._repository.save(task)

    async def delete_task(self, task_id: int) -> Optional[Task]:
        task = await self._repository.get_by_id(task_id)
        if task is None:
            return None
        await self._repository.delete(task)
        return task

    async def find_active_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> list[Task]:
        """Найти активные задачи пользователя по подстроке названия."""
        query = title_query.strip().lower()
        tasks = await self.list_active_tasks(telegram_user_id)
        return [task for task in tasks if query in task.title.lower()]

    async def complete_task_by_title(
        self, telegram_user_id: int, title_query: str
    ) -> Optional[Task]:
        matches = await self.find_active_by_title(telegram_user_id, title_query)
        if not matches:
            return None
        task = matches[0]
        task.status = COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        return await self._repository.save(task)

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

    async def mark_reminded(self, task_id: int) -> Optional[Task]:
        task = await self._repository.get_by_id(task_id)
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
