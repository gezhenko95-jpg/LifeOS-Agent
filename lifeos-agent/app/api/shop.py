"""
REST API магазина наград (specs/028-farm-tamagotchi-rewards.md, фаза 1).

Эндпоинты не содержат бизнес-логики — только вызывают ShopService и
переводят его исключения в HTTP-коды.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import build_shop_service
from app.db.session import get_session
from app.shop.catalog import KIND_TITLES
from app.shop.schemas import PurchaseRequest, ShopItemRead, ShopStateRead
from app.shop.service import (
    AlreadyOwnedError,
    InsufficientCoinsError,
    ShopService,
    ShopState,
    UnknownItemError,
)

router = APIRouter(prefix="/shop", tags=["shop"])


def get_shop_service(session: AsyncSession = Depends(get_session)) -> ShopService:
    return build_shop_service(session)


def _to_read(state: ShopState) -> ShopStateRead:
    return ShopStateRead(
        earned_coins=state.earned_coins,
        spent_coins=state.spent_coins,
        balance=state.balance,
        items=[
            ShopItemRead(
                id=entry.item.id,
                kind=entry.item.kind,
                kind_title=KIND_TITLES[entry.item.kind],
                title=entry.item.title,
                emoji=entry.item.emoji,
                price=entry.item.price,
                description=entry.item.description,
                repeatable=entry.item.repeatable,
                owned=entry.owned,
                affordable=entry.affordable,
                available_until=entry.item.available_until,
            )
            for entry in state.items
        ],
    )


@router.get("/state", response_model=ShopStateRead)
async def get_state(
    telegram_user_id: int, service: ShopService = Depends(get_shop_service)
) -> ShopStateRead:
    """Каталог вместе с кошельком: витрина без баланса бесполезна, а два
    отдельных запроса на один экран дали бы фронту момент, когда цена уже
    видна, а хватает ли монет — ещё нет."""
    return _to_read(await service.get_state(telegram_user_id))


@router.post("/purchase", response_model=ShopStateRead)
async def purchase(
    payload: PurchaseRequest, service: ShopService = Depends(get_shop_service)
) -> ShopStateRead:
    """Возвращает НОВОЕ состояние кошелька и витрины целиком — фронту не
    нужно догружать состояние вторым запросом после покупки."""
    try:
        state = await service.purchase(payload.telegram_user_id, payload.item_id)
    except UnknownItemError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (InsufficientCoinsError, AlreadyOwnedError) as exc:
        # 409, а не 400: запрос сам по себе корректен, покупка невозможна
        # из-за состояния кошелька/инвентаря на этот момент.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return _to_read(state)
