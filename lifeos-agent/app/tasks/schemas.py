"""
Pydantic-схемы для Tasks Service.

Схемы описывают контракт API. Бизнес-логики здесь нет.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """Данные для создания задачи."""

    telegram_user_id: int
    title: str = Field(min_length=1, max_length=255)
    due_date: Optional[datetime] = None
    priority: str = "normal"
    recurrence: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, max_length=20)


class TaskUpdate(BaseModel):
    """Данные для частичного обновления задачи."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    due_date: Optional[datetime] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    recurrence: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, max_length=20)


class TaskStats(BaseModel):
    """Сводка по задачам для /ui (см. app/api/tasks.py)."""

    completed_this_week: int


class TaskRead(BaseModel):
    """Представление задачи в ответах API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    title: str
    description: Optional[str] = None
    color: Optional[str] = None
    due_date: Optional[datetime]
    status: str
    priority: str
    recurrence: Optional[str]
    completed_at: Optional[datetime]
    created_at: datetime
