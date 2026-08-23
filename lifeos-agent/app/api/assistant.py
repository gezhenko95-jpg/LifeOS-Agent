"""
REST API для настройки персонажа (specs/020-butler-personas.md).

Эндпоинты не содержат бизнес-логики — только вызывают AssistantService.
Переключатель живёт только на /ui, в боте его нет (см. спеку).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.schemas import PersonaRead, PersonaUpdate
from app.assistant.service import AssistantService
from app.core.container import build_assistant_service
from app.db.session import get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_assistant_service(
    session: AsyncSession = Depends(get_session),
) -> AssistantService:
    return build_assistant_service(session)


@router.get("/persona", response_model=PersonaRead)
async def get_persona(
    telegram_user_id: int,
    service: AssistantService = Depends(get_assistant_service),
) -> PersonaRead:
    persona = await service.get_persona(telegram_user_id)
    return PersonaRead(telegram_user_id=telegram_user_id, persona=persona)


@router.put("/persona", response_model=PersonaRead)
async def set_persona(
    payload: PersonaUpdate,
    service: AssistantService = Depends(get_assistant_service),
) -> PersonaRead:
    persona = await service.set_persona(payload.telegram_user_id, payload.persona)
    return PersonaRead(telegram_user_id=payload.telegram_user_id, persona=persona)
