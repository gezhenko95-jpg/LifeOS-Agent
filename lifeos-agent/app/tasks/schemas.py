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
    parent_id: Optional[int] = None
    contact_id: Optional[int] = None
    habit_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """Данные для частичного обновления задачи."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    due_date: Optional[datetime] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    recurrence: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, max_length=20)
    contact_id: Optional[int] = None
    # None у contact_id означает "не трогать" (как везде в TaskUpdate) —
    # отдельный флаг для явного снятия привязки (тот же приём, что
    # clear_reminder/clear_description у привычек).
    clear_contact: bool = False
    habit_id: Optional[int] = None
    clear_habit: bool = False


class TaskStats(BaseModel):
    """Сводка по задачам для /ui (см. app/api/tasks.py)."""

    completed_this_week: int


class TaskRead(BaseModel):
    """Представление задачи в ответах API.

    subtask_count/comment_count не колонки Task — считаются пачкой на
    весь список (см. app/tasks/repository.py::count_subtasks_by_parents),
    поэтому не заполняются автоматически через from_attributes и
    проставляются в app/api/tasks.py после model_validate.
    """

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
    in_progress: bool = False
    in_progress_started_at: Optional[datetime] = None
    parent_id: Optional[int] = None
    subtask_count: int = 0
    comment_count: int = 0
    contact_id: Optional[int] = None
    habit_id: Optional[int] = None


class TaskCommentCreate(BaseModel):
    telegram_user_id: int
    text: str = Field(min_length=1, max_length=1000)


class TaskCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    telegram_user_id: int
    text: str
    created_at: datetime
