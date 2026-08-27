"""
Pydantic-схемы фермы.
"""

from datetime import datetime

from pydantic import BaseModel


class PlotRead(BaseModel):
    id: int
    planted_at: datetime
    ready_at: datetime
    fertilized: bool
    hay_yield: int
    ready: bool


class FarmStateRead(BaseModel):
    available_seeds: int
    available_fertilizer: int
    available_rain: int
    available_hay: int
    plots: list[PlotRead]


class PlantRequest(BaseModel):
    telegram_user_id: int
    use_fertilizer: bool = False


class TelegramUserRequest(BaseModel):
    """Общее тело для действий без параметров, кроме владельца —
    сбор урожая указывает грядку в пути, полив её вообще не требует."""

    telegram_user_id: int
