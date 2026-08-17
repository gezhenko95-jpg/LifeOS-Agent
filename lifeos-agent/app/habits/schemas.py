"""
Pydantic-схемы для Habits Service.
"""

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HabitCreate(BaseModel):
    """Данные для создания привычки."""

    telegram_user_id: int
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=255)
    reminder_time: Optional[time] = None


class HabitUpdate(BaseModel):
    """Частичное обновление привычки.

    `None` означает «не трогать поле», поэтому для снятия описания и
    напоминания есть отдельные флаги — иначе нельзя было бы отличить
    «оставь как есть» от «убери» (см. HabitService.update_habit).
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=255)
    reminder_time: Optional[time] = None
    clear_description: bool = False
    clear_reminder: bool = False


class HabitRead(BaseModel):
    """Представление привычки в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    title: str
    description: Optional[str] = None
    reminder_time: Optional[time] = None
    archived: bool
    created_at: datetime
    streak: int = 0
