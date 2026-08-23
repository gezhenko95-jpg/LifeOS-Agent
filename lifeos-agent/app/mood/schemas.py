"""
Pydantic-схемы для Mood Service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.mood.models import MAX_SCORE, MIN_SCORE


class MoodEntryCreate(BaseModel):
    telegram_user_id: int
    score: int = Field(ge=MIN_SCORE, le=MAX_SCORE)
    note: Optional[str] = Field(default=None, max_length=500)


class MoodEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    score: int
    note: Optional[str] = None
    logged_at: datetime
