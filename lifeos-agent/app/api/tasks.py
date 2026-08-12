"""
REST API для задач.

Эндпоинты не содержат бизнес-логики — только вызывают TaskService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.tasks.repository import TaskRepository
from app.tasks.schemas import TaskCreate, TaskRead, TaskUpdate
from app.tasks.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(TaskRepository(session))


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
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    telegram_user_id: int, service: TaskService = Depends(get_task_service)
) -> list[TaskRead]:
    tasks = await service.list_active_tasks(telegram_user_id)
    return [TaskRead.model_validate(task) for task in tasks]


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    try:
        task = await service.update_task(
            task_id=task_id,
            title=payload.title,
            due_date=payload.due_date,
            status=payload.status,
            priority=payload.priority,
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
    task_id: int, service: TaskService = Depends(get_task_service)
) -> None:
    task = await service.delete_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена"
        )
