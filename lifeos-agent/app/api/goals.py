"""
REST API для целей.

Эндпоинты не содержат бизнес-логики — только вызывают GoalService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.goals.repository import GoalRepository
from app.goals.schemas import GoalCreate, GoalRead, GoalUpdate
from app.goals.service import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_service(session: AsyncSession = Depends(get_session)) -> GoalService:
    return GoalService(GoalRepository(session))


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate, service: GoalService = Depends(get_goal_service)
) -> GoalRead:
    try:
        goal = await service.create_goal(
            telegram_user_id=payload.telegram_user_id,
            title=payload.title,
            target_date=payload.target_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return GoalRead.model_validate(goal)


@router.get("", response_model=list[GoalRead])
async def list_goals(
    telegram_user_id: int, service: GoalService = Depends(get_goal_service)
) -> list[GoalRead]:
    goals = await service.list_active_goals(telegram_user_id)
    return [GoalRead.model_validate(goal) for goal in goals]


@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal(
    goal_id: int,
    telegram_user_id: int,
    payload: GoalUpdate,
    service: GoalService = Depends(get_goal_service),
) -> GoalRead:
    try:
        goal = await service.update_goal(
            telegram_user_id=telegram_user_id,
            goal_id=goal_id,
            title=payload.title,
            target_date=payload.target_date,
            status=payload.status,
            progress=payload.progress,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена"
        )
    return GoalRead.model_validate(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    telegram_user_id: int,
    service: GoalService = Depends(get_goal_service),
) -> None:
    goal = await service.delete_goal(telegram_user_id, goal_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена"
        )
