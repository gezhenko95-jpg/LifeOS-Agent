"""
Pydantic-схемы для Watchlist Service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    """Данные для создания записи."""

    telegram_user_id: int
    title: str = Field(min_length=1, max_length=255)
    media_type: str = "other"


class WatchlistRead(BaseModel):
    """Представление записи в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    title: str
    media_type: str
    status: str
    source: str
    drive_file_url: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
