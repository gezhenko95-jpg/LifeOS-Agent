"""
REST API для долговременной памяти.

Эндпоинты не содержат бизнес-логики — только вызывают MemoryService.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.memory.models import MemoryType
from app.memory.repository import MemoryRepository
from app.memory.schemas import MemoryEntryCreate, MemoryEntryRead, MemoryEntryUpdate
from app.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


def get_memory_service(session: AsyncSession = Depends(get_session)) -> MemoryService:
    return MemoryService(MemoryRepository(session))


@router.post("", response_model=MemoryEntryRead, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: MemoryEntryCreate, service: MemoryService = Depends(get_memory_service)
) -> MemoryEntryRead:
    try:
        entry = await service.save(
            telegram_user_id=payload.telegram_user_id,
            type=payload.type,
            content=payload.content,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return MemoryEntryRead.model_validate(entry)


@router.get("", response_model=list[MemoryEntryRead])
async def list_entries(
    telegram_user_id: int,
    type: Optional[MemoryType] = None,
    q: Optional[str] = None,
    service: MemoryService = Depends(get_memory_service),
) -> list[MemoryEntryRead]:
    if q:
        entries = await service.search(telegram_user_id, q, type=type)
    else:
        entries = await service.list_entries(telegram_user_id, type=type)
    return [MemoryEntryRead.model_validate(entry) for entry in entries]


@router.get("/context", response_model=list[MemoryEntryRead])
async def get_context(
    telegram_user_id: int,
    limit: int = 10,
    service: MemoryService = Depends(get_memory_service),
) -> list[MemoryEntryRead]:
    entries = await service.get_context(telegram_user_id, limit=limit)
    return [MemoryEntryRead.model_validate(entry) for entry in entries]


@router.patch("/{entry_id}", response_model=MemoryEntryRead)
async def update_entry(
    entry_id: int,
    telegram_user_id: int,
    payload: MemoryEntryUpdate,
    service: MemoryService = Depends(get_memory_service),
) -> MemoryEntryRead:
    entry = await service.update(
        telegram_user_id=telegram_user_id,
        entry_id=entry_id,
        content=payload.content,
        archived=payload.archived,
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        )
    return MemoryEntryRead.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: int,
    telegram_user_id: int,
    service: MemoryService = Depends(get_memory_service),
) -> None:
    entry = await service.delete(telegram_user_id, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        )
