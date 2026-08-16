"""
REST API для мини-игры "🪙 Зайди и забери" (ежедневный чек-ин, /ui).

Эндпоинты не содержат бизнес-логики — только вызывают RewardsService.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.rewards.repository import RewardsRepository
from app.rewards.schemas import CheckinRequest, RewardsStatusRead
from app.rewards.service import RewardsService

router = APIRouter(prefix="/rewards", tags=["rewards"])


def get_rewards_service(
    session: AsyncSession = Depends(get_session),
) -> RewardsService:
    return RewardsService(RewardsRepository(session))


@router.get("/status", response_model=RewardsStatusRead)
async def get_status(
    telegram_user_id: int, service: RewardsService = Depends(get_rewards_service)
) -> RewardsStatusRead:
    status_ = await service.get_status(telegram_user_id)
    return RewardsStatusRead(
        claimed_today=status_.claimed_today,
        streak=status_.streak,
        total_coins=status_.total_coins,
    )


@router.post("/checkin", response_model=RewardsStatusRead)
async def claim_checkin(
    payload: CheckinRequest, service: RewardsService = Depends(get_rewards_service)
) -> RewardsStatusRead:
    """Идемпотентно: повторный вызов в тот же день не даёт монет дважды,
    просто возвращает уже известное состояние (claimed_today=true)."""
    status_ = await service.claim_today(payload.telegram_user_id)
    return RewardsStatusRead(
        claimed_today=status_.claimed_today,
        streak=status_.streak,
        total_coins=status_.total_coins,
    )
