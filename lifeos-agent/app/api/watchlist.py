"""
REST API для Watchlist.

Эндпоинты не содержат бизнес-логики — только вызывают WatchlistService.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.watchlist.books import get_books_client
from app.watchlist.repository import WatchlistRepository
from app.watchlist.schemas import WatchlistCreate, WatchlistRead
from app.watchlist.service import WatchlistService
from app.watchlist.tmdb import get_tmdb_client

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def get_watchlist_service(
    session: AsyncSession = Depends(get_session),
) -> WatchlistService:
    return WatchlistService(WatchlistRepository(session))


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: WatchlistCreate, service: WatchlistService = Depends(get_watchlist_service)
) -> WatchlistRead:
    try:
        item = await service.create_item(
            telegram_user_id=payload.telegram_user_id,
            title=payload.title,
            media_type=payload.media_type,
            # Добавление с сайта должно давать такую же карточку с
            # обложкой, как из бота, — иначе полка выглядит по-разному в
            # зависимости от того, откуда запись пришла.
            tmdb_client=get_tmdb_client(),
            books_client=get_books_client(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return WatchlistRead.model_validate(item)


@router.get("", response_model=list[WatchlistRead])
async def list_items(
    telegram_user_id: int, service: WatchlistService = Depends(get_watchlist_service)
) -> list[WatchlistRead]:
    """Все статусы разом (to_watch + done) — "полка" в /ui сама
    раскладывает по секциям на фронте, не гоняем два запроса."""
    items = await service.list_all_items(telegram_user_id)
    return [WatchlistRead.model_validate(item) for item in items]


@router.post("/{item_id}/complete", response_model=WatchlistRead)
async def complete_item(
    item_id: int,
    telegram_user_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistRead:
    item = await service.mark_done(telegram_user_id, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        )
    return WatchlistRead.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    telegram_user_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    item = await service.delete_item(telegram_user_id, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        )
