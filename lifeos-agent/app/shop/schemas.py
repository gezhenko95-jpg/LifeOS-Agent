"""
Pydantic-схемы магазина.
"""

from pydantic import BaseModel


class ShopItemRead(BaseModel):
    id: str
    kind: str
    kind_title: str
    title: str
    emoji: str
    price: int
    description: str
    repeatable: bool
    owned: int
    affordable: bool


class ShopStateRead(BaseModel):
    earned_coins: int
    spent_coins: int
    balance: int
    items: list[ShopItemRead]


class PurchaseRequest(BaseModel):
    telegram_user_id: int
    item_id: str
