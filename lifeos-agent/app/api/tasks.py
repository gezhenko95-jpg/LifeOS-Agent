"""
REST API для задач.

Эндпоинты не содержат бизнес-логики — только вызывают TaskService.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_task_comment_service, build_task_service
from app.db.session import get_session
from app.tasks.schemas import (
    TaskCommentCreate,
    TaskCommentRead,
    TaskCreate,
    TaskRead,
    TaskStats,
    TaskUpdate,
)
from app.tasks.service import TaskCommentService, TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])

_WEEK = timedelta(days=7)


def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return build_task_service(session)


def get_task_comment_service(
    session: AsyncSession = Depends(get_session),
) -> TaskCommentService:
    return build_task_comment_service(session)


async def _with_counts(
    tasks: list,
    telegram_user_id: int,
    service: TaskService,
    comment_service: TaskCommentService,
) -> list[TaskRead]:
    """Проставить subtask_count/comment_count поверх model_validate — см.
    docstring TaskRead в schemas.py."""
    ids = [t.id for t in tasks]
    subtask_counts = await service.count_subtasks_by_parents(telegram_user_id, ids)
    comment_counts = await comment_service.count_by_tasks(ids)
    out = []
    for task in tasks:
        read = TaskRead.model_validate(task)
        read.subtask_count = subtask_counts.get(task.id, 0)
        read.comment_count = comment_counts.get(task.id, 0)
        out.append(read)
    return out


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    try:
        task = await service.create_task(
            telegram_user_id=payload.telegram_user_id,
            title=payload.title,
            due_date=payload.due_date,
            priority=payload.priority,
            recurrence=payload.recurrence,
            description=payload.description,
            color=payload.color,
            parent_id=payload.parent_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    telegram_user_id: int,
    service: TaskService = Depends(get_task_service),
    comment_service: TaskCommentService = Depends(get_task_comment_service),
) -> list[TaskRead]:
    tasks = await service.list_active_tasks(telegram_user_id)
    return await _with_counts(tasks, telegram_user_id, service, comment_service)


@router.get("/{task_id}/subtasks", response_model=list[TaskRead])
async def list_subtasks(
    task_id: int,
    telegram_user_id: int,
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    tasks = await service.list_subtasks(telegram_user_id, task_id)
    return [TaskRead.model_validate(task) for task in tasks]


@router.post("/{task_id}/in-progress", response_model=TaskRead)
async def toggle_in_progress(
    task_id: int,
    telegram_user_id: int,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    task = await service.toggle_in_progress(telegram_user_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена"
        )
    return TaskRead.model_validate(task)


@router.get("/{task_id}/comments", response_model=list[TaskCommentRead])
async def list_comments(
    task_id: int,
    telegram_user_id: int,
    service: TaskCommentService = Depends(get_task_comment_service),
) -> list[TaskCommentRead]:
    comments = await service.list_comments(telegram_user_id, task_id)
    return [TaskCommentRead.model_validate(c) for c in comments]


@router.post(
    "/{task_id}/comments",
    response_model=TaskCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    task_id: int,
    payload: TaskCommentCreate,
    service: TaskCommentService = Depends(get_task_comment_service),
) -> TaskCommentRead:
    try:
        comment = await service.add_comment(
            payload.telegram_user_id, task_id, payload.text
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена"
        )
    return TaskCommentRead.model_validate(comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    telegram_user_id: int,
    service: TaskCommentService = Depends(get_task_comment_service),
) -> None:
    comment = await service.delete_comment(telegram_user_id, comment_id)
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Комментарий не найден"
        )


@router.get("/completed", response_model=list[TaskRead])
async def list_completed_tasks(
    telegram_user_id: int,
    since: datetime,
    until: datetime,
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    """Выполненные в [since, until) — для календаря на /ui (зачёркнутые
    задачи в день, когда их отметили готовыми). Существующий сервисный
    метод (Personal Insights) уже делал ровно это, роута не было."""
    tasks = await service.list_tasks_completed_between(telegram_user_id, since, until)
    return [TaskRead.model_validate(task) for task in tasks]


@router.get("/stats", response_model=TaskStats)
async def get_task_stats(
    telegram_user_id: int, service: TaskService = Depends(get_task_service)
) -> TaskStats:
    """Для карточки "Итоги недели" в /ui (см. app/web/static/index.html)."""
    since = datetime.now(timezone.utc) - _WEEK
    completed = await service.count_tasks_completed_since(telegram_user_id, since)
    return TaskStats(completed_this_week=completed)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    telegram_user_id: int,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    try:
        task = await service.update_task(
            telegram_user_id=telegram_user_id,
            task_id=task_id,
            title=payload.title,
            due_date=payload.due_date,
            status=payload.status,
            priority=payload.priority,
            recurrence=payload.recurrence,
            description=payload.description,
            color=payload.color,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена"
        )
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    telegram_user_id: int,
    service: TaskService = Depends(get_task_service),
) -> None:
    task = await service.delete_task(telegram_user_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена"
        )
