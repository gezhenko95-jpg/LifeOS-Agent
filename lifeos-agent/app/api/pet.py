"""
REST API питомца (specs/028-farm-tamagotchi-rewards.md, фаза 3).

Эндпоинты не содержат бизнес-логики — только вызывают PetService и
переводят его исключения в HTTP-коды.
"""

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_pet_service
from app.db.session import get_session
from app.farm.service import InsufficientHayError
from app.pet.schemas import PetStatusRead, TelegramUserRequest
from app.pet.service import (
    AlreadyHasPetError,
    NoPetError,
    NotDeadError,
    PetError,
    PetIsDeadError,
    PetService,
    PetStatus,
)

router = APIRouter(prefix="/pet", tags=["pet"])


def get_pet_service(session: AsyncSession = Depends(get_session)) -> PetService:
    return build_pet_service(session)


def _to_read(status_: PetStatus) -> PetStatusRead:
    return PetStatusRead.model_validate(status_, from_attributes=True)


def _raise_for(exc: PetError | InsufficientHayError) -> NoReturn:
    # 404 — питомца ещё нет, 409 — запрос корректен, но невозможен из-за
    # текущего состояния (уже есть питомец, он мёртв/жив). Тот же выбор
    # кодов, что в app/api/farm.py и app/api/shop.py.
    if isinstance(exc, NoPetError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/status", response_model=PetStatusRead)
async def get_status(
    telegram_user_id: int, service: PetService = Depends(get_pet_service)
) -> PetStatusRead:
    return _to_read(await service.get_status(telegram_user_id))


@router.post("/adopt", response_model=PetStatusRead)
async def adopt(
    payload: TelegramUserRequest, service: PetService = Depends(get_pet_service)
) -> PetStatusRead:
    try:
        status_ = await service.adopt(payload.telegram_user_id)
    except AlreadyHasPetError as exc:
        _raise_for(exc)
    return _to_read(status_)


@router.post("/feed", response_model=PetStatusRead)
async def feed(
    payload: TelegramUserRequest, service: PetService = Depends(get_pet_service)
) -> PetStatusRead:
    try:
        status_ = await service.feed(payload.telegram_user_id)
    except (NoPetError, PetIsDeadError, InsufficientHayError) as exc:
        _raise_for(exc)
    return _to_read(status_)


@router.post("/revive", response_model=PetStatusRead)
async def revive(
    payload: TelegramUserRequest, service: PetService = Depends(get_pet_service)
) -> PetStatusRead:
    try:
        status_ = await service.revive(payload.telegram_user_id)
    except (NoPetError, NotDeadError) as exc:
        _raise_for(exc)
    return _to_read(status_)
