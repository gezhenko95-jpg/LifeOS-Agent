"""Pydantic-схемы для FocusSessionService."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.focus.service import DEFAULT_BREAK_MINUTES, DEFAULT_WORK_MINUTES


class FocusSessionCreate(BaseModel):
    telegram_user_id: int
    work_minutes: int = Field(default=DEFAULT_WORK_MINUTES, gt=0)
    break_minutes: int = Field(default=DEFAULT_BREAK_MINUTES, gt=0)
    task_id: Optional[int] = None


class FocusSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    task_id: Optional[int] = None
    work_minutes: int
    break_minutes: int
    started_at: datetime
    work_ends_at: datetime
    break_ends_at: Optional[datetime] = None
    status: str


class FocusStatsRead(BaseModel):
    completed_count: int
    total_minutes: int
