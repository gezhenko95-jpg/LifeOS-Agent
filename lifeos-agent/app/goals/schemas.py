"""
Pydantic-схемы для Goals Service.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GoalCreate(BaseModel):
    """Данные для создания цели."""

    telegram_user_id: int
    title: str = Field(min_length=1, max_length=255)
    target_date: Optional[date] = None


class GoalUpdate(BaseModel):
    """Данные для частичного обновления цели."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    target_date: Optional[date] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    description: Optional[str] = Field(default=None, max_length=500)


class GoalRead(BaseModel):
    """Представление цели в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    title: str
    description: Optional[str] = None
    target_date: Optional[date]
    progress: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    # Не колонка Goal — побочный атрибут GoalService.update_goal
    # (specs/030), заполняется через getattr в app/api/goals.py.
    reward_coins: int = 0
