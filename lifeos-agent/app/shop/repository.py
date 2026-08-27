"""
Репозиторий движений монет.

Единственное место с SQL к таблице `coin_transactions`. Бизнес-логика
(хватает ли монет, можно ли купить второй раз) — в service.py.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shop.models import PURCHASE, CoinTransaction


class ShopRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_transaction(
        self,
        telegram_user_id: int,
        amount: int,
        reason: str,
        item_id: str | None = None,
    ) -> CoinTransaction:
        transaction = CoinTransaction(
            telegram_user_id=telegram_user_id,
            amount=amount,
            reason=reason,
            item_id=item_id,
        )
        self._session.add(transaction)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def net_amount(self, telegram_user_id: int) -> int:
        """Сумма всех движений со знаком: сколько монет ушло (или, при
        будущих начислениях мимо чек-ина, добавилось) сверх заработанного
        визитами. Пустая история — 0, а не None (SUM по нулю строк в SQL
        возвращает NULL)."""
        query = select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
            CoinTransaction.telegram_user_id == telegram_user_id
        )
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def purchased_counts(self, telegram_user_id: int) -> dict[str, int]:
        """Инвентарь: сколько раз куплен каждый товар. Отдельной таблицы
        инвентаря нет — он выводится из истории покупок (см. докстринг
        CoinTransaction).

        Расход расходуемых предметов (ферма съедает семя, ускоритель
        сгорает) появится вместе с самой фермой — вычитать его будет
        домен app/farm/ из СВОЕГО учёта, эти числа останутся "сколько
        всего куплено за всю историю"."""
        query = (
            select(CoinTransaction.item_id, func.count())
            .where(
                CoinTransaction.telegram_user_id == telegram_user_id,
                CoinTransaction.reason == PURCHASE,
                CoinTransaction.item_id.is_not(None),
            )
            .group_by(CoinTransaction.item_id)
        )
        result = await self._session.execute(query)
        return {item_id: count for item_id, count in result.all()}
