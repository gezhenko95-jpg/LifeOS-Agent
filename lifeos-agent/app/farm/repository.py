"""
Репозиторий фермы — единственное место с SQL к `farm_plots`/
`farm_supply_use`/`hay_consumption`. Бизнес-логика (хватает ли семян,
созрела ли грядка) — в service.py.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import owned_or_none
from app.farm.models import FarmPlot, FarmSupplyUse, HayConsumption


def _as_aware(value: datetime) -> datetime:
    """SQLite не хранит tzinfo — значение из БД может прийти naive, даже
    если писали aware (см. HANDOFF.md, «Технические нюансы», п.3). Нужно
    здесь же, не только в service.py: push_ready_at_earlier сравнивает
    ready_at, прочитанный из БД, с floor, который приходит от вызывающей
    стороны уже aware."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class FarmRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Грядки -----------------------------------------------------

    async def add_plot(self, plot: FarmPlot) -> FarmPlot:
        self._session.add(plot)
        await self._session.commit()
        await self._session.refresh(plot)
        return plot

    async def get_plot(self, plot_id: int) -> FarmPlot | None:
        return await self._session.get(FarmPlot, plot_id)

    async def get_own_plot(
        self, telegram_user_id: int, plot_id: int
    ) -> FarmPlot | None:
        """owned_or_none — тот же приём владения по telegram_user_id, что
        уже применяют фокус-сессии/задачи (app/core/ownership.py): чужой
        id грядки не должен быть виден как 404 ИЛИ как "не твоё" —
        снаружи оба случая выглядят одинаково, это и есть цель."""
        return owned_or_none(await self.get_plot(plot_id), telegram_user_id)

    async def list_active_plots(self, telegram_user_id: int) -> list[FarmPlot]:
        """Не собранные грядки — растущие и уже созревшие, но лежащие в
        поле. Используется и для отображения статуса, и чтобы применить
        "Тёплый дождь" сразу ко всем."""
        query = (
            select(FarmPlot)
            .where(
                FarmPlot.telegram_user_id == telegram_user_id,
                FarmPlot.harvested_at.is_(None),
            )
            .order_by(FarmPlot.planted_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def mark_harvested(self, plot: FarmPlot, when: datetime) -> FarmPlot:
        plot.harvested_at = when
        self._session.add(plot)
        await self._session.commit()
        await self._session.refresh(plot)
        return plot

    async def push_ready_at_earlier(
        self, plots: list[FarmPlot], hours: int, floor: datetime
    ) -> None:
        """Полив: у каждой переданной грядки ready_at сдвигается назад на
        `hours`, не раньше `floor` (обычно "сейчас" — грядка не может
        стать готовой в будущем относительно текущего момента задним
        числом сильнее, чем "уже готова")."""
        for plot in plots:
            current = _as_aware(plot.ready_at)
            plot.ready_at = max(current - timedelta(hours=hours), floor)
            self._session.add(plot)
        await self._session.commit()

    async def total_planted(self, telegram_user_id: int) -> int:
        """Сколько грядок засеяно за всю историю — расход семян
        (app/shop/catalog.py::seed_clover) считается по этому числу, не
        отдельным счётчиком."""
        query = select(func.count()).where(
            FarmPlot.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def total_fertilized(self, telegram_user_id: int) -> int:
        query = select(func.count()).where(
            FarmPlot.telegram_user_id == telegram_user_id,
            FarmPlot.fertilized.is_(True),
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def total_harvested_hay(self, telegram_user_id: int) -> int:
        query = select(func.coalesce(func.sum(FarmPlot.hay_yield), 0)).where(
            FarmPlot.telegram_user_id == telegram_user_id,
            FarmPlot.harvested_at.is_not(None),
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    # --- Расход семян/ускорителей ------------------------------------

    async def record_supply_use(
        self, telegram_user_id: int, item_id: str, quantity: int = 1
    ) -> None:
        self._session.add(
            FarmSupplyUse(
                telegram_user_id=telegram_user_id,
                item_id=item_id,
                quantity=quantity,
            )
        )
        await self._session.commit()

    async def supply_used_counts(self, telegram_user_id: int) -> dict[str, int]:
        query = (
            select(
                FarmSupplyUse.item_id,
                func.coalesce(func.sum(FarmSupplyUse.quantity), 0),
            )
            .where(FarmSupplyUse.telegram_user_id == telegram_user_id)
            .group_by(FarmSupplyUse.item_id)
        )
        result = await self._session.execute(query)
        return {item_id: int(total) for item_id, total in result.all()}

    # --- Сено ---------------------------------------------------------

    async def total_hay_consumed(self, telegram_user_id: int) -> int:
        query = select(func.coalesce(func.sum(HayConsumption.amount), 0)).where(
            HayConsumption.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def record_hay_consumption(self, telegram_user_id: int, amount: int) -> None:
        self._session.add(
            HayConsumption(telegram_user_id=telegram_user_id, amount=amount)
        )
        await self._session.commit()
