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
    # Карточка из TMDb (см. app/watchlist/tmdb.py) — всё опционально:
    # книги, отсутствие ключа и промахи поиска оставляют поля пустыми.
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    release_year: Optional[int] = None
    drive_file_url: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
