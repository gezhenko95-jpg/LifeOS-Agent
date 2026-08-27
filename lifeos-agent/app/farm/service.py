"""
FarmService — вся бизнес-логика фермы (specs/028-farm-tamagotchi-
rewards.md, фаза 2). Repository — только БД, API — только вызывает
этот сервис.

Composite: ферма не хранит СВОЙ склад семян/ускорителей отдельной
таблицей — она спрашивает у ShopRepository, сколько куплено, и вычитает
СВОЙ расход (app/farm/models.py::FarmSupplyUse). Тот же приём, что уже
применён в app/shop/service.py для монет (спрашивает у RewardsService).
Рост грядки — тот же класс задачи, что и фокус-сессии
(app/focus/service.py): момент времени в БД (ready_at), опрос при
каждом чтении статуса, без фоновой джобы-тика (см. HANDOFF, «Технические
нюансы», п.1 — актуально и здесь, хотя в фазе 2 нет уведомления, только
статус по запросу).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.farm.models import FarmPlot
from app.farm.repository import FarmRepository
from app.shop.catalog import BOOSTER, SEED, get_item
from app.shop.repository import ShopRepository

# Калибровка экономики — ответ владельца 27.08 (specs/028): грядка растёт
# сутки и даёт 10 сена, семя стоит 30 монет (см. app/shop/catalog.py).
GROW_HOURS = 24
HAY_PER_PLOT = 10
# Удобрение ускоряет вдвое, а не на фиксированное число часов — растёт
# вместе с GROW_HOURS, если он когда-нибудь изменится.
FERTILIZER_GROW_HOURS = GROW_HOURS // 2
RAIN_REDUCE_HOURS = 6

SEED_ITEM_ID = "seed_clover"
FERTILIZER_ITEM_ID = "booster_fertilizer"
RAIN_ITEM_ID = "booster_rain"


class FarmError(ValueError):
    """Общий предок ошибок фермы — API ловит его одним except."""


class NoSeedsError(FarmError):
    pass


class NoBoosterError(FarmError):
    pass


class PlotNotFoundError(FarmError):
    pass


class PlotNotReadyError(FarmError):
    pass


class InsufficientHayError(FarmError):
    """Не про UI фермы — эту ошибку ловит app/pet/service.py при кормлении."""


@dataclass
class PlotStatus:
    id: int
    planted_at: datetime
    ready_at: datetime
    fertilized: bool
    hay_yield: int
    ready: bool


@dataclass
class FarmState:
    available_seeds: int
    available_fertilizer: int
    available_rain: int
    available_hay: int
    plots: list[PlotStatus]


class FarmService:
    def __init__(
        self, repository: FarmRepository, shop_repository: ShopRepository
    ) -> None:
        self._repository = repository
        self._shop = shop_repository

    async def get_state(self, telegram_user_id: int) -> FarmState:
        return await self._state(telegram_user_id)

    async def plant(
        self, telegram_user_id: int, use_fertilizer: bool = False
    ) -> FarmState:
        available_seeds, available_fertilizer, _, _ = await self._supplies(
            telegram_user_id
        )
        if available_seeds <= 0:
            raise NoSeedsError("Нет семян — купите в Магазине")
        if use_fertilizer and available_fertilizer <= 0:
            raise NoBoosterError("Нет удобрения — купите в Магазине")

        now = datetime.now(timezone.utc)
        grow_hours = FERTILIZER_GROW_HOURS if use_fertilizer else GROW_HOURS
        plot = FarmPlot(
            telegram_user_id=telegram_user_id,
            planted_at=now,
            ready_at=now + timedelta(hours=grow_hours),
            fertilized=use_fertilizer,
            hay_yield=HAY_PER_PLOT,
        )
        await self._repository.add_plot(plot)
        await self._repository.record_supply_use(telegram_user_id, SEED_ITEM_ID)
        if use_fertilizer:
            await self._repository.record_supply_use(
                telegram_user_id, FERTILIZER_ITEM_ID
            )
        return await self._state(telegram_user_id)

    async def harvest(self, telegram_user_id: int, plot_id: int) -> FarmState:
        plot = await self._repository.get_own_plot(telegram_user_id, plot_id)
        if plot is None:
            raise PlotNotFoundError("Нет такой грядки")
        if plot.harvested_at is not None:
            raise PlotNotFoundError("Эта грядка уже собрана")
        now = datetime.now(timezone.utc)
        ready_at = _as_aware(plot.ready_at)
        if now < ready_at:
            raise PlotNotReadyError("Ещё не созрела")
        await self._repository.mark_harvested(plot, now)
        return await self._state(telegram_user_id)

    async def apply_rain(self, telegram_user_id: int) -> FarmState:
        _, _, available_rain, _ = await self._supplies(telegram_user_id)
        if available_rain <= 0:
            raise NoBoosterError("Нет «Тёплого дождя» — купите в Магазине")
        active = await self._repository.list_active_plots(telegram_user_id)
        now = datetime.now(timezone.utc)
        if active:
            # floor=now: полив не делает грядку "готовой в будущем
            # отрицательно" — просто ускоряет, максимум до "уже готова".
            await self._repository.push_ready_at_earlier(
                active, RAIN_REDUCE_HOURS, floor=now
            )
        # Расходуется даже если грядок нет — это решение пользователя
        # нажать кнопку, а не гарантия результата; проверка active выше
        # существует только чтобы не гонять пустой UPDATE по всем нулям.
        await self._repository.record_supply_use(telegram_user_id, RAIN_ITEM_ID)
        return await self._state(telegram_user_id)

    # --- Сено, используется app/pet/service.py -----------------------

    async def available_hay(self, telegram_user_id: int) -> int:
        harvested = await self._repository.total_harvested_hay(telegram_user_id)
        consumed = await self._repository.total_hay_consumed(telegram_user_id)
        return harvested - consumed

    async def consume_hay(self, telegram_user_id: int, amount: int) -> int:
        """Списывает сено на кормление питомца. Возвращает остаток ПОСЛЕ
        списания. Не проверяет достаточность сама — вызывающая сторона
        (app/pet/service.py) обязана проверить available_hay заранее,
        чтобы решить, кормить ли вообще; здесь только бухгалтерия."""
        await self._repository.record_hay_consumption(telegram_user_id, amount)
        return await self.available_hay(telegram_user_id)

    # --- internals ------------------------------------------------

    async def _supplies(self, telegram_user_id: int) -> tuple[int, int, int, int]:
        purchased = await self._shop.purchased_counts(telegram_user_id)
        used = await self._repository.supply_used_counts(telegram_user_id)
        seeds = purchased.get(SEED_ITEM_ID, 0) - used.get(SEED_ITEM_ID, 0)
        fertilizer = purchased.get(FERTILIZER_ITEM_ID, 0) - used.get(
            FERTILIZER_ITEM_ID, 0
        )
        rain = purchased.get(RAIN_ITEM_ID, 0) - used.get(RAIN_ITEM_ID, 0)
        hay = await self.available_hay(telegram_user_id)
        return seeds, fertilizer, rain, hay

    async def _state(self, telegram_user_id: int) -> FarmState:
        seeds, fertilizer, rain, hay = await self._supplies(telegram_user_id)
        active = await self._repository.list_active_plots(telegram_user_id)
        now = datetime.now(timezone.utc)
        plots = [
            PlotStatus(
                id=plot.id,
                planted_at=plot.planted_at,
                ready_at=plot.ready_at,
                fertilized=plot.fertilized,
                hay_yield=plot.hay_yield,
                ready=now >= _as_aware(plot.ready_at),
            )
            for plot in active
        ]
        return FarmState(
            available_seeds=max(seeds, 0),
            available_fertilizer=max(fertilizer, 0),
            available_rain=max(rain, 0),
            available_hay=max(hay, 0),
            plots=plots,
        )


def _as_aware(value: datetime) -> datetime:
    """SQLite не хранит tzinfo — значение из БД может прийти naive, даже
    если писали aware (см. HANDOFF.md, «Технические нюансы», п.3, тот же
    приём, что в app/tasks/formatting.py::to_local)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _check_catalog_ids() -> None:
    """Опечатка в SEED_ITEM_ID/FERTILIZER_ITEM_ID/RAIN_ITEM_ID сломала бы
    расход/остаток тихо: get_item вернул бы None, а purchased.get(...)
    для несуществующего ключа читал бы 0 — выглядело бы как "магазин не
    даёт купить", а не как баг фермы. Проверка на импорте ловит это сразу
    вместо живого сюрприза на проде."""
    for item_id, kind in (
        (SEED_ITEM_ID, SEED),
        (FERTILIZER_ITEM_ID, BOOSTER),
        (RAIN_ITEM_ID, BOOSTER),
    ):
        item = get_item(item_id)
        assert item is not None and item.kind == kind, (
            f"app/farm/service.py: {item_id!r} должен быть в каталоге "
            f"(app/shop/catalog.py) с kind={kind!r}"
        )


_check_catalog_ids()
