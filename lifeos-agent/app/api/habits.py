"""
REST API для привычек.

Эндпоинты не содержат бизнес-логики — только вызывают HabitService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.habits.models import Habit
from app.habits.repository import HabitRepository
from app.habits.schemas import HabitCreate, HabitRead
from app.habits.service import HabitService

router = APIRouter(prefix="/habits", tags=["habits"])


def get_habit_service(session: AsyncSession = Depends(get_session)) -> HabitService:
    return HabitService(HabitRepository(session))


async def _to_read_model(habit: Habit, service: HabitService) -> HabitRead:
    streak = await service.get_streak(habit.id)
    read_model = HabitRead.model_validate(habit)
    return read_model.model_copy(update={"streak": streak})


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
async def create_habit(
    payload: HabitCreate, service: HabitService = Depends(get_habit_service)
) -> HabitRead:
    try:
        habit = await service.create_habit(
            telegram_user_id=payload.telegram_user_id, title=payload.title
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return await _to_read_model(habit, service)


@router.get("", response_model=list[HabitRead])
async def list_habits(
    telegram_user_id: int, service: HabitService = Depends(get_habit_service)
) -> list[HabitRead]:
    habits = await service.list_active_habits(telegram_user_id)
    return [await _to_read_model(habit, service) for habit in habits]


@router.post("/{habit_id}/complete", response_model=HabitRead)
async def complete_habit(
    habit_id: int, service: HabitService = Depends(get_habit_service)
) -> HabitRead:
    habit = await service.mark_done_by_id(habit_id)
    if habit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена"
        )
    return await _to_read_model(habit, service)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: int, service: HabitService = Depends(get_habit_service)
) -> None:
    habit = await service.delete_habit(habit_id)
    if habit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена"
        )
