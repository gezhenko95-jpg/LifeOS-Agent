"""
Rewards Service — ежедневный чек-ин мини-игры "🪙 Зайди и забери".

Вся бизнес-логика здесь. Repository — только БД, API — только вызывает
этот сервис. Расчёт монет/стрика — детерминированный код (ADR-004),
никакого AI: app/rewards/coins.py + app.habits.streaks.current_streak
(переиспользован как есть — "чек-ин за день" структурно то же самое,
что и лог привычки, см. докстринг Checkin).
"""

from dataclasses import dataclass
from datetime import date

from app.habits.streaks import current_streak
from app.rewards.coins import total_coins
from app.rewards.repository import RewardsRepository


@dataclass
class RewardsStatus:
    claimed_today: bool
    streak: int
    total_coins: int


class RewardsService:
    def __init__(self, repository: RewardsRepository) -> None:
        self._repository = repository

    async def claim_today(self, telegram_user_id: int) -> RewardsStatus:
        """Отметить сегодняшний визит, если ещё не отмечен. Идемпотентно
        — повторный клик "забрать" в тот же день не даёт монет дважды
        (claimed_today в ответе как раз и говорит фронту не радоваться
        второй раз)."""
        today = date.today()
        already = await self._repository.has_checkin_on(telegram_user_id, today)
        if not already:
            await self._repository.add_checkin(telegram_user_id, today)
        return await self._status(telegram_user_id, today)

    async def get_status(self, telegram_user_id: int) -> RewardsStatus:
        return await self._status(telegram_user_id, date.today())

    async def _status(self, telegram_user_id: int, today: date) -> RewardsStatus:
        days = await self._repository.list_days(telegram_user_id)
        return RewardsStatus(
            claimed_today=today in days,
            streak=current_streak(days, today),
            total_coins=total_coins(days),
        )
