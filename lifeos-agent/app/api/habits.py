"""
REST API для привычек.

Эндпоинты не содержат бизнес-логики — только вызывают HabitService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_habit_service
from app.db.session import get_session
from app.habits.models import Habit
from app.habits.schemas import (
    HabitCreate,
    HabitRead,
    HabitUpdate,
    StreakFreezeWalletRead,
)
from app.habits.service import (
    HabitFreezeError,
    HabitNotFoundError,
    HabitService,
)

router = APIRouter(prefix="/habits", tags=["habits"])


def get_habit_service(session: AsyncSession = Depends(get_session)) -> HabitService:
    return build_habit_service(session)


async def _to_read_model(habit: Habit, service: HabitService) -> HabitRead:
    streak = await service.get_streak(habit.telegram_user_id, habit.id)
    can_freeze = await service.can_freeze_yesterday_bulk(
        habit.telegram_user_id, [habit.id]
    )
    read_model = HabitRead.model_validate(habit)
    return read_model.model_copy(
        update={
            "streak": streak,
            "can_freeze_yesterday": can_freeze.get(habit.id, False),
        }
    )


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
async def create_habit(
    payload: HabitCreate, service: HabitService = Depends(get_habit_service)
) -> HabitRead:
    try:
        habit = await service.create_habit(
            telegram_user_id=payload.telegram_user_id,
            title=payload.title,
            description=payload.description,
            reminder_time=payload.reminder_time,
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
    habit_ids = [h.id for h in habits]
    streaks = await service.get_streaks_bulk(telegram_user_id, habit_ids)
    can_freeze = await service.can_freeze_yesterday_bulk(telegram_user_id, habit_ids)
    return [
        HabitRead.model_validate(habit).model_copy(
            update={
                "streak": streaks.get(habit.id, 0),
                "can_freeze_yesterday": can_freeze.get(habit.id, False),
            }
        )
        for habit in habits
    ]


@router.patch("/{habit_id}", response_model=HabitRead)
async def update_habit(
    habit_id: int,
    telegram_user_id: int,
    payload: HabitUpdate,
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    """Правка привычки с сайта. У привычек PATCH не было вовсе —
    название, описание и время напоминания можно было задать только при
    создании."""
    try:
        habit = await service.update_habit(
            telegram_user_id=telegram_user_id,
            habit_id=habit_id,
            title=payload.title,
            description=payload.description,
            reminder_time=payload.reminder_time,
            clear_description=payload.clear_description,
            clear_reminder=payload.clear_reminder,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if habit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена"
        )
    return await _to_read_model(habit, service)


@router.post("/{habit_id}/complete", response_model=HabitRead)
async def complete_habit(
    habit_id: int,
    telegram_user_id: int,
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    habit = await service.mark_done_by_id(telegram_user_id, habit_id)
    if habit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена"
        )
    return await _to_read_model(habit, service)


@router.get("/streak-freezes", response_model=StreakFreezeWalletRead)
async def get_streak_freeze_wallet(
    telegram_user_id: int, service: HabitService = Depends(get_habit_service)
) -> StreakFreezeWalletRead:
    available = await service.available_freezes(telegram_user_id)
    return StreakFreezeWalletRead(available=available)


@router.post("/{habit_id}/streak-freeze", response_model=HabitRead)
async def use_streak_freeze(
    habit_id: int,
    telegram_user_id: int,
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    """Заморозить вчерашний день привычки (specs/029). 404 — привычка не
    найдена/чужая; 409 — нет заморозок в инвентаре или замораживать
    нечего (см. HabitService.freeze_yesterday)."""
    try:
        habit = await service.freeze_yesterday(telegram_user_id, habit_id)
    except HabitNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except HabitFreezeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return await _to_read_model(habit, service)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: int,
    telegram_user_id: int,
    service: HabitService = Depends(get_habit_service),
) -> None:
    habit = await service.delete_habit(telegram_user_id, habit_id)
    if habit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена"
        )
