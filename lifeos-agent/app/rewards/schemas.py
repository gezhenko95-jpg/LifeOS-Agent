"""
Pydantic-схемы для Rewards Service.
"""

from pydantic import BaseModel


class CheckinRequest(BaseModel):
    telegram_user_id: int


class RewardsStatusRead(BaseModel):
    claimed_today: bool
    streak: int
    total_coins: int
