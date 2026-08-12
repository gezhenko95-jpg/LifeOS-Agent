"""
Pydantic-схемы для Habits Service.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HabitCreate(BaseModel):
    """Данные для создания привычки."""

    telegram_user_id: int
    title: str = Field(min_length=1, max_length=255)


class HabitRead(BaseModel):
    """Представление привычки в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    title: str
    archived: bool
    created_at: datetime
    streak: int = 0
