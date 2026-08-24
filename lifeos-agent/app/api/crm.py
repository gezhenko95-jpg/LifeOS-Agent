"""
REST API для личного CRM (specs/018-personal-crm.md).

Эндпоинты не содержат бизнес-логики — только вызывают ContactService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import (
    build_contact_comment_service,
    build_contact_service,
    build_task_service,
)
from app.crm.schemas import (
    ContactCommentCreate,
    ContactCommentRead,
    ContactCreate,
    ContactRead,
    ContactUpdate,
)
from app.crm.service import ContactCommentService, ContactService
from app.db.session import get_session
from app.tasks.schemas import TaskRead
from app.tasks.service import TaskService

router = APIRouter(prefix="/crm", tags=["crm"])


def get_contact_service(
    session: AsyncSession = Depends(get_session),
) -> ContactService:
    return build_contact_service(session)


def get_contact_comment_service(
    session: AsyncSession = Depends(get_session),
) -> ContactCommentService:
    return build_contact_comment_service(session)


def get_task_service_for_crm(
    session: AsyncSession = Depends(get_session),
) -> TaskService:
    """Свой провайдер, не переиспользуем get_task_service из app/api/tasks.py
    — он приватный модульный хелпер того файла, а не общий контракт."""
    return build_task_service(session)


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
            tags=payload.tags,
            nudge_after_days=payload.nudge_after_days,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ContactRead.model_validate(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: int,
    telegram_user_id: int,
    payload: ContactUpdate,
    service: ContactService = Depends(get_contact_service),
) -> ContactRead:
    try:
        contact = await service.update_contact(
            telegram_user_id=telegram_user_id,
            contact_id=contact_id,
            name=payload.name,
            notes=payload.notes,
            tags=payload.tags,
            nudge_after_days=payload.nudge_after_days,
            clear_nudge_after_days=payload.clear_nudge_after_days,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден"
        )
    return ContactRead.model_validate(contact)


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    telegram_user_id: int,
    service: ContactService = Depends(get_contact_service),
    comment_service: ContactCommentService = Depends(get_contact_comment_service),
) -> list[ContactRead]:
    contacts = await service.list_contacts(telegram_user_id)
    ids = [c.id for c in contacts]
    comment_counts = await comment_service.count_by_contacts(ids)
    out = []
    for contact in contacts:
        read = ContactRead.model_validate(contact)
        read.comment_count = comment_counts.get(contact.id, 0)
        out.append(read)
    return out


@router.get("/contacts/{contact_id}/tasks", response_model=list[TaskRead])
async def list_contact_tasks(
    contact_id: int,
    telegram_user_id: int,
    service: TaskService = Depends(get_task_service_for_crm),
) -> list[TaskRead]:
    tasks = await service.list_tasks_for_contact(telegram_user_id, contact_id)
    return [TaskRead.model_validate(task) for task in tasks]


@router.get("/contacts/{contact_id}/comments", response_model=list[ContactCommentRead])
async def list_contact_comments(
    contact_id: int,
    telegram_user_id: int,
    service: ContactCommentService = Depends(get_contact_comment_service),
) -> list[ContactCommentRead]:
    comments = await service.list_comments(telegram_user_id, contact_id)
    return [ContactCommentRead.model_validate(c) for c in comments]


@router.post(
    "/contacts/{contact_id}/comments",
    response_model=ContactCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact_comment(
    contact_id: int,
    payload: ContactCommentCreate,
    service: ContactCommentService = Depends(get_contact_comment_service),
) -> ContactCommentRead:
    try:
        comment = await service.add_comment(
            payload.telegram_user_id, contact_id, payload.text
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден"
        )
    return ContactCommentRead.model_validate(comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact_comment(
    comment_id: int,
    telegram_user_id: int,
    service: ContactCommentService = Depends(get_contact_comment_service),
) -> None:
    comment = await service.delete_comment(telegram_user_id, comment_id)
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Комментарий не найден"
        )


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
