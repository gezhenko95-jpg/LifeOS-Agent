"""
Pydantic-схемы для Contact Service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    """Данные для создания контакта."""

    telegram_user_id: int
    name: str = Field(min_length=1, max_length=100)
    birthday_month: Optional[int] = Field(default=None, ge=1, le=12)
    birthday_day: Optional[int] = Field(default=None, ge=1, le=31)
    notes: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[str] = Field(default=None, max_length=200)
    nudge_after_days: Optional[int] = Field(default=None, ge=1)


class ContactUpdate(BaseModel):
    """Частичное обновление — раньше единственным способом изменить
    контакт было удалить и создать заново."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[str] = Field(default=None, max_length=200)
    nudge_after_days: Optional[int] = Field(default=None, ge=1)
    clear_nudge_after_days: bool = False


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    name: str
    birthday_month: Optional[int] = None
    birthday_day: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    nudge_after_days: Optional[int] = None
    last_contact_at: datetime
    created_at: datetime
