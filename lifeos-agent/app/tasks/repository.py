"""
Репозиторий для задач.

Единственное место, где выполняются SQL-запросы к таблице `tasks`.
Никакой бизнес-логики — только чтение/запись.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from app.core.repository import BaseRepository, escape_like
from app.tasks.models import Task, TaskComment


class TaskRepository(BaseRepository[Task]):
    """Доступ к таблице `tasks` через AsyncSession."""

    model = Task

    async def list_by_user(
        self,
        telegram_user_id: int,
        status: Optional[str] = None,
        top_level_only: bool = False,
    ) -> list[Task]:
        query = select(Task).where(Task.telegram_user_id == telegram_user_id)
        if status is not None:
            query = query.where(Task.status == status)
        if top_level_only:
            # Подзадачи не дублируются в общем списке — видны только через
            # родителя (list_subtasks). Иначе плоский список задач
            # захламлялся бы и родителем, и каждой его подзадачей.
            query = query.where(Task.parent_id.is_(None))
        query = query.order_by(Task.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_contact(
        self, telegram_user_id: int, contact_id: int
    ) -> list[Task]:
        """Задачи, связанные с контактом CRM — обратная сторона
        Task.contact_id (отчёт владельца 24.08, вечер #6, волна 3:
        "нажимая на человека хочу видеть какие задачи с ним связаны")."""
        query = (
            select(Task)
            .where(
                Task.telegram_user_id == telegram_user_id,
                Task.contact_id == contact_id,
            )
            .order_by(Task.created_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_subtasks(self, telegram_user_id: int, parent_id: int) -> list[Task]:
        """Дочерние задачи родителя `parent_id` — сам родитель фильтрует
        по владельцу отдельно (owned_or_none в сервисе), здесь только
        второй слой защиты: чужой parent_id не вернёт чужие подзадачи."""
        query = (
            select(Task)
            .where(
                Task.telegram_user_id == telegram_user_id,
                Task.parent_id == parent_id,
            )
            .order_by(Task.created_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_subtasks_by_parents(
        self, telegram_user_id: int, parent_ids: list[int]
    ) -> dict[int, int]:
        """Сколько подзадач у каждого id из `parent_ids` — одним запросом
        для целого списка (список задач рисуется весь сразу, N+1 на
        каждую задачу отдельным запросом было бы AUDIT.md-находкой)."""
        if not parent_ids:
            return {}
        query = (
            select(Task.parent_id, func.count())
            .where(
                Task.telegram_user_id == telegram_user_id,
                Task.parent_id.in_(parent_ids),
            )
            .group_by(Task.parent_id)
        )
        result = await self._session.execute(query)
        return {parent_id: count for parent_id, count in result.all()}

    async def find_active_by_title(
        self, telegram_user_id: int, needle: str
    ) -> list[Task]:
        """Активные задачи, чьё название содержит needle — фильтр в БД
        (см. AUDIT.md, P-2), а не "загрузить все активные и отфильтровать
        в Python". Порядок — created_at, как у list_by_user; приоритетную
        пересортировку делает TaskService (набор совпадений маленький,
        сортировать его в Python дёшево)."""
        query = select(Task).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "active",
            Task.title.ilike(f"%{escape_like(needle)}%", escape="\\"),
        )
        query = query.order_by(Task.created_at)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_due_unreminded(self, now: datetime) -> list[Task]:
        """Активные задачи с наступившим сроком, по которым ещё не напомнили."""
        query = select(Task).where(
            Task.status == "active",
            Task.due_date.is_not(None),
            Task.due_date <= now,
            Task.reminded_at.is_(None),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_completed_since(
        self, telegram_user_id: int, since: datetime
    ) -> int:
        """Сколько задач пользователя завершено, начиная с `since`.

        Без фильтра по telegram_user_id не обойтись здесь (в отличие от
        list_due_unreminded) — дайджест персональный, а не общесистемный.
        """
        query = select(func.count()).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def count_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> int:
        """Сколько задач завершено в полуоткрытом интервале [since, until) —
        для графика "по неделям" (см. app/scheduler/charts.py)."""
        query = select(func.count()).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
            Task.completed_at < until,
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def list_completed_between(
        self, telegram_user_id: int, since: datetime, until: datetime
    ) -> list[Task]:
        """Как count_completed_between, но возвращает сами задачи — нужны
        completed_at/due_date для находок Personal Insights
        (см. app/insights/service.py, specs/009-personal-insights.md)."""
        query = select(Task).where(
            Task.telegram_user_id == telegram_user_id,
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
            Task.completed_at < until,
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())


class TaskCommentRepository(BaseRepository[TaskComment]):
    """Доступ к таблице `task_comments`. Отдельный класс, не методы
    TaskRepository — разные модели, ADR-005 (один сервис/репозиторий —
    одна ответственность)."""

    model = TaskComment

    async def list_by_task(self, task_id: int) -> list[TaskComment]:
        query = (
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_by_tasks(self, task_ids: list[int]) -> dict[int, int]:
        """Число комментариев на каждую задачу из `task_ids` — одним
        запросом, тот же приём, что count_subtasks_by_parents."""
        if not task_ids:
            return {}
        query = (
            select(TaskComment.task_id, func.count())
            .where(TaskComment.task_id.in_(task_ids))
            .group_by(TaskComment.task_id)
        )
        result = await self._session.execute(query)
        return {task_id: count for task_id, count in result.all()}
