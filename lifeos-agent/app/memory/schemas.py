"""
Pydantic-схемы для Memory Service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.memory.models import MemoryType


class MemoryEntryCreate(BaseModel):
    """Данные для создания записи памяти."""

    telegram_user_id: int
    type: MemoryType
    content: str = Field(min_length=1)
    source: str = "manual"


class MemoryEntryUpdate(BaseModel):
    """Данные для частичного обновления записи памяти."""

    content: Optional[str] = Field(default=None, min_length=1)
    archived: Optional[bool] = None


class MemoryEntryRead(BaseModel):
    """Представление записи памяти в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    type: MemoryType
    content: str
    source: str
    archived: bool
    created_at: datetime
    updated_at: Optional[datetime]
