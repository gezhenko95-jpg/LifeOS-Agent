"""
REST API для дайджестов Telegram-каналов (см. specs/015-digest-api.md).

Эндпоинты не содержат бизнес-логики — только вызывают DigestService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import get_ai_client
from app.core.container import build_digest_service
from app.db.session import get_session
from app.digest.schemas import (
    DigestChannelCreate,
    DigestChannelRead,
    DigestCreate,
    DigestRead,
    DigestSendResult,
)
from app.digest.service import DigestService
from app.telegram.notifier import NotifyError, send_to_owner

router = APIRouter(prefix="/digest", tags=["digest"])


def get_digest_service(session: AsyncSession = Depends(get_session)) -> DigestService:
    return build_digest_service(session)


@router.get("", response_model=list[DigestRead])
async def list_digests(
    telegram_user_id: int, service: DigestService = Depends(get_digest_service)
) -> list[DigestRead]:
    digests = await service.list_digests(telegram_user_id)
    result = []
    for digest in digests:
        channels = await service.list_channels(digest.id)
        result.append(
            DigestRead(
                id=digest.id,
                telegram_user_id=digest.telegram_user_id,
                name=digest.name,
                auto_frequency=digest.auto_frequency,
                created_at=digest.created_at,
                channels=[DigestChannelRead.model_validate(c) for c in channels],
            )
        )
    return result


@router.post("", response_model=DigestRead, status_code=status.HTTP_201_CREATED)
async def create_digest(
    payload: DigestCreate, service: DigestService = Depends(get_digest_service)
) -> DigestRead:
    try:
        digest = await service.create_digest(
            telegram_user_id=payload.telegram_user_id,
            name=payload.name,
            auto_frequency=payload.auto_frequency,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    # Новая тема всегда без каналов — лишний запрос в БД не делаем.
    return DigestRead(
        id=digest.id,
        telegram_user_id=digest.telegram_user_id,
        name=digest.name,
        auto_frequency=digest.auto_frequency,
        created_at=digest.created_at,
        channels=[],
    )


@router.post(
    "/{digest_id}/channels",
    response_model=DigestChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel(
    digest_id: int,
    payload: DigestChannelCreate,
    service: DigestService = Depends(get_digest_service),
) -> DigestChannelRead:
    try:
        channel = await service.add_channel_by_id(
            telegram_user_id=payload.telegram_user_id,
            digest_id=digest_id,
            channel_username=payload.channel_username,
        )
    except ValueError as exc:
        # Канал уже в теме или не читается — вина ввода, не сервера.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тема дайджеста не найдена"
        )
    return DigestChannelRead.model_validate(channel)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel(
    channel_id: int,
    telegram_user_id: int,
    service: DigestService = Depends(get_digest_service),
) -> None:
    digest = await service.remove_channel_by_id(telegram_user_id, channel_id)
    if digest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден"
        )


@router.post("/{digest_id}/send", response_model=DigestSendResult)
async def send_digest(
    digest_id: int,
    telegram_user_id: int,
    service: DigestService = Depends(get_digest_service),
) -> DigestSendResult:
    """Собрать дайджест и прислать его в Telegram.

    Текст возвращается в ответе ВСЕГДА, когда он собран, — даже если
    отправка не удалась. Сборка уже сдвинула водяной знак и закоммитила
    его, поэтому промолчать об ошибке значит потерять посты навсегда:
    следующий прогон их уже не увидит (см. specs/015-digest-api.md).
    """
    try:
        text = await service.build_digest_text_by_id(
            telegram_user_id, digest_id, ai_client=get_ai_client()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if text is None:
        # Не ошибка: ровно так же тихо пропускает фоновая джоба.
        return DigestSendResult(delivered=False, text=None)

    try:
        await send_to_owner(text)
    except NotifyError as exc:
        return DigestSendResult(delivered=False, text=text, error=str(exc))

    return DigestSendResult(delivered=True, text=text)
