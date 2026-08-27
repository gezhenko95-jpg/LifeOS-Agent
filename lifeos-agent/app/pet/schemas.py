"""
Pydantic-схемы питомца.
"""

from datetime import datetime

from pydantic import BaseModel


class PetStatusRead(BaseModel):
    exists: bool
    hunger: int = 0
    mood: int = 0
    state: str | None = None
    last_fed_at: datetime | None = None
    deaths_count: int = 0
    next_threshold_at: datetime | None = None


class TelegramUserRequest(BaseModel):
    telegram_user_id: int
