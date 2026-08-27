"""
REST API фермы (specs/028-farm-tamagotchi-rewards.md, фаза 2).

Эндпоинты не содержат бизнес-логики — только вызывают FarmService и
переводят его исключения в HTTP-коды.
"""

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_farm_service
from app.db.session import get_session
from app.farm.schemas import FarmStateRead, PlantRequest, TelegramUserRequest
from app.farm.service import (
    FarmError,
    FarmService,
    FarmState,
    NoBoosterError,
    NoSeedsError,
    PlotNotFoundError,
    PlotNotReadyError,
)

router = APIRouter(prefix="/farm", tags=["farm"])


def get_farm_service(session: AsyncSession = Depends(get_session)) -> FarmService:
    return build_farm_service(session)


def _to_read(state: FarmState) -> FarmStateRead:
    return FarmStateRead.model_validate(state, from_attributes=True)


def _raise_for(exc: FarmError) -> NoReturn:
    # 404 — того, к чему обращались, не существует; 409 — запрос
    # корректен, но невозможен из-за текущего состояния (нет семян,
    # грядка ещё растёт). Тот же выбор кодов, что в app/api/shop.py.
    # NoReturn — чтобы вызывающему коду не казалось, что после
    # `_raise_for(exc)` возможно продолжение с неприсвоенной переменной.
    if isinstance(exc, PlotNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/state", response_model=FarmStateRead)
async def get_state(
    telegram_user_id: int, service: FarmService = Depends(get_farm_service)
) -> FarmStateRead:
    return _to_read(await service.get_state(telegram_user_id))


@router.post("/plant", response_model=FarmStateRead)
async def plant(
    payload: PlantRequest, service: FarmService = Depends(get_farm_service)
) -> FarmStateRead:
    try:
        state = await service.plant(
            payload.telegram_user_id, use_fertilizer=payload.use_fertilizer
        )
    except (NoSeedsError, NoBoosterError) as exc:
        _raise_for(exc)
    return _to_read(state)


@router.post("/plots/{plot_id}/harvest", response_model=FarmStateRead)
async def harvest(
    plot_id: int,
    payload: TelegramUserRequest,
    service: FarmService = Depends(get_farm_service),
) -> FarmStateRead:
    try:
        state = await service.harvest(payload.telegram_user_id, plot_id)
    except (PlotNotFoundError, PlotNotReadyError) as exc:
        _raise_for(exc)
    return _to_read(state)


@router.post("/rain", response_model=FarmStateRead)
async def apply_rain(
    payload: TelegramUserRequest, service: FarmService = Depends(get_farm_service)
) -> FarmStateRead:
    try:
        state = await service.apply_rain(payload.telegram_user_id)
    except NoBoosterError as exc:
        _raise_for(exc)
    return _to_read(state)
