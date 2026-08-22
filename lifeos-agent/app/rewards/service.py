"""
Rewards Service — ежедневный чек-ин мини-игры "🪙 Зайди и забери".

Вся бизнес-логика здесь. Repository — только БД, API — только вызывает
этот сервис. Расчёт монет/стрика/удачи — детерминированный код
(ADR-004), никакого AI: app/rewards/coins.py + app.habits.streaks
.current_streak (переиспользован как есть — "чек-ин за день" структурно
то же самое, что и лог привычки, см. докстринг Checkin).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError

from app.habits.streaks import current_streak
from app.rewards import coins
from app.rewards.repository import RewardsRepository


@dataclass
class RewardsStatus:
    claimed_today: bool
    streak: int
    total_coins: int
    # Про СЕГОДНЯШНИЙ день конкретно — фронту нужно знать, что именно
    # произошло при последнем клике "Забрать" (сколько дали и не был ли
    # день "счастливым"), а не только новую сумму всего накопленного.
    coins_today: int
    lucky_today: bool


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
            try:
                await self._repository.add_checkin(telegram_user_id, today)
            except IntegrityError:
                # Гонка: два почти одновременных клика "Забрать" (двойной
                # тап, ретрай после таймаута) оба проходят has_checkin_on
                # как False. UniqueConstraint uq_checkin_day ловит второй
                # insert — день всё равно уже отмечен первым запросом,
                # значит вести себя нужно идемпотентно, а не падать 500-й.
                await self._repository.rollback()
        return await self._status(telegram_user_id, today)

    async def get_status(self, telegram_user_id: int) -> RewardsStatus:
        return await self._status(telegram_user_id, date.today())

    async def _status(self, telegram_user_id: int, today: date) -> RewardsStatus:
        days = await self._repository.list_days(telegram_user_id)
        streak = current_streak(days, today)
        claimed_today = today in days
        # Удача решена (детерминированно, см. coins.is_lucky_day) в любом
        # случае, но раскрываем её фронту, только если день УЖЕ забран —
        # до клика это был бы спойлер сюрприза, а не награда.
        #
        # Вызов ЧЕРЕЗ МОДУЛЬ (coins.is_lucky_day), а не через прямой
        # импорт имени — принципиально для тестов: total_coins() ниже
        # тоже вызывает is_lucky_day, но СВОЙ внутренний, определённый в
        # том же модуле coins.py. Патч одного изолированного импортированного
        # имени в этом файле не подействовал бы на внутренний вызов
        # total_coins, и в тестах два места давали бы разные (реальные
        # vs замоканные) результаты для одного и того же дня. Вызов через
        # модуль — одна точка патчинга на оба места.
        lucky_today = claimed_today and coins.is_lucky_day(telegram_user_id, today)
        return RewardsStatus(
            claimed_today=claimed_today,
            streak=streak,
            total_coins=coins.total_coins(days, telegram_user_id),
            coins_today=(
                coins.coins_for_streak_day(streak, lucky_today) if claimed_today else 0
            ),
            lucky_today=lucky_today,
        )
