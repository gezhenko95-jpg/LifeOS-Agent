"""
Pydantic-схемы для Digest Service (см. specs/015-digest-api.md).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Те же значения, что в сервисе (DAILY/WEEKLY). Literal, а не свободная
# строка: опечатка "dayly" иначе доехала бы до БД и тихо отключила
# автоотправку — тема просто перестала бы приходить.
AutoFrequency = Literal["daily", "weekly"]


class DigestCreate(BaseModel):
    """Данные для создания темы дайджеста."""

    telegram_user_id: int
    name: str = Field(min_length=1, max_length=50)
    auto_frequency: Optional[AutoFrequency] = None


class DigestChannelCreate(BaseModel):
    """Данные для добавления канала в тему."""

    telegram_user_id: int
    channel_username: str = Field(min_length=1, max_length=64)


class DigestChannelRead(BaseModel):
    """Канал внутри темы."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    digest_id: int
    channel_username: str
    last_seen_post_id: Optional[int]
    added_at: datetime


class DigestRead(BaseModel):
    """Тема вместе со своими каналами.

    Каналы вложены, а не отдаются отдельным запросом на тему: тем у
    человека единицы, а N+1 запрос ради экономии одного JOIN — ровно та
    проблема, которую уже чинили у привычек (AUDIT.md, P-1).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    name: str
    auto_frequency: Optional[str]
    created_at: datetime
    channels: list[DigestChannelRead] = []


class DigestSendResult(BaseModel):
    """Результат «прислать новое».

    `text` возвращается ВСЕГДА, когда он собран, — даже если отправка в
    Telegram не удалась. Причина: сборка текста уже сдвинула водяной
    знак и закоммитила его, так что посты считаются прочитанными. Без
    текста в ответе они были бы потеряны безвозвратно (см. раздел
    «Отправка» в specs/015-digest-api.md).
    """

    delivered: bool
    text: Optional[str] = None
    error: Optional[str] = None
