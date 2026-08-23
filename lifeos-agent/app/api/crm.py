"""
REST API для личного CRM (specs/018-personal-crm.md).

Эндпоинты не содержат бизнес-логики — только вызывают ContactService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_contact_service
from app.crm.schemas import ContactCreate, ContactRead
from app.crm.service import ContactService
from app.db.session import get_session

router = APIRouter(prefix="/crm", tags=["crm"])


def get_contact_service(
    session: AsyncSession = Depends(get_session),
) -> ContactService:
    return build_contact_service(session)


@router.post(
    "/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED
)
async def create_contact(
    payload: ContactCreate,
    service: ContactService = Depends(get_contact_service),
) -> ContactRead:
    try:
        contact = await service.add_contact(
            telegram_user_id=payload.telegram_user_id,
            name=payload.name,
            birthday_month=payload.birthday_month,
            birthday_day=payload.birthday_day,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ContactRead.model_validate(contact)


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    telegram_user_id: int,
    service: ContactService = Depends(get_contact_service),
) -> list[ContactRead]:
    contacts = await service.list_contacts(telegram_user_id)
    return [ContactRead.model_validate(c) for c in contacts]


@router.post("/contacts/{contact_id}/contacted", response_model=ContactRead)
async def mark_contacted(
    contact_id: int,
    telegram_user_id: int,
    service: ContactService = Depends(get_contact_service),
) -> ContactRead:
    contact = await service.mark_contacted(telegram_user_id, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден"
        )
    return ContactRead.model_validate(contact)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    telegram_user_id: int,
    service: ContactService = Depends(get_contact_service),
) -> None:
    contact = await service.delete_contact(telegram_user_id, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден"
        )
