"""
ShopService — покупка за монеты (specs/028, фаза 1).

Вся бизнес-логика здесь: repository знает только SQL, API — только
переводит исключения в HTTP-коды. Никакого AI — цены и правила покупки
детерминированы (ADR-004), это игровая арифметика, а не суждение.

Заработок монет сервис не считает сам, а спрашивает у RewardsService —
единственного владельца этой механики (чек-ины, серия, счастливые дни).
Магазин добавляет ровно одно: вычитание.
"""

from dataclasses import dataclass

from app.rewards.service import RewardsService
from app.shop.catalog import CATALOG, ShopItem, get_item
from app.shop.models import PURCHASE
from app.shop.repository import ShopRepository


class ShopError(ValueError):
    """Общий предок ошибок магазина — API ловит его одним except."""


class UnknownItemError(ShopError):
    pass


class InsufficientCoinsError(ShopError):
    pass


class AlreadyOwnedError(ShopError):
    pass


@dataclass
class ShopItemState:
    item: ShopItem
    # Сколько раз куплен. Для разовых украшений это 0 или 1 — фронту
    # хватает одного поля на оба вида товара, отдельного owned: bool нет.
    owned: int
    affordable: bool


@dataclass
class ShopState:
    # Заработано за всё время (checkins) — оно же остаётся основой для
    # званий/тем/достижений в /ui: покупка НЕ должна отбирать открытую
    # палитру или понижать звание, иначе трата монет наказывала бы.
    earned_coins: int
    # Ушло из баланса (earned − balance).
    spent_coins: int
    balance: int
    items: list[ShopItemState]


class ShopService:
    def __init__(
        self, repository: ShopRepository, rewards_service: RewardsService
    ) -> None:
        self._repository = repository
        self._rewards = rewards_service

    async def get_state(self, telegram_user_id: int) -> ShopState:
        earned, balance, owned = await self._wallet(telegram_user_id)
        return self._state(earned, balance, owned)

    async def purchase(self, telegram_user_id: int, item_id: str) -> ShopState:
        item = get_item(item_id)
        if item is None:
            raise UnknownItemError(f"Нет такого товара: {item_id}")

        earned, balance, owned = await self._wallet(telegram_user_id)
        if not item.repeatable and owned.get(item.id, 0) > 0:
            raise AlreadyOwnedError(f"«{item.title}» уже куплен")
        if balance < item.price:
            raise InsufficientCoinsError(
                f"Не хватает монет: нужно {item.price}, есть {balance}"
            )

        # Запись со знаком минус — единственное место во всём проекте, где
        # баланс уменьшается.
        #
        # Гонка двух одновременных покупок теоретически может увести
        # баланс в минус (оба запроса читают старый баланс до записи).
        # Сознательно не закрыто блокировкой: приложение однопользо-
        # вательское, а цена ошибки — несколько монет в игровой валюте,
        # тогда как SELECT ... FOR UPDATE тянет за собой транзакционную
        # обвязку, которой больше нигде в проекте нет. Ledger append-only,
        # так что "минус" в худшем случае виден и правится записью
        # компенсации, а не потерян.
        await self._repository.add_transaction(
            telegram_user_id=telegram_user_id,
            amount=-item.price,
            reason=PURCHASE,
            item_id=item.id,
        )

        owned = dict(owned)
        owned[item.id] = owned.get(item.id, 0) + 1
        return self._state(earned, balance - item.price, owned)

    async def _wallet(self, telegram_user_id: int) -> tuple[int, int, dict[str, int]]:
        status = await self._rewards.get_status(telegram_user_id)
        net = await self._repository.net_amount(telegram_user_id)
        owned = await self._repository.purchased_counts(telegram_user_id)
        return status.total_coins, status.total_coins + net, owned

    def _state(self, earned: int, balance: int, owned: dict[str, int]) -> ShopState:
        return ShopState(
            earned_coins=earned,
            spent_coins=earned - balance,
            balance=balance,
            items=[
                ShopItemState(
                    item=item,
                    owned=owned.get(item.id, 0),
                    # "Могу купить прямо сейчас" — не только про деньги:
                    # уже купленное разовое украшение недоступно при любом
                    # балансе, и кнопка на фронте гаснет по этому же полю.
                    affordable=balance >= item.price
                    and (item.repeatable or owned.get(item.id, 0) == 0),
                )
                for item in CATALOG
            ],
        )
