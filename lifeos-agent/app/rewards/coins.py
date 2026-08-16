"""
Чистые функции начисления монеток за ежедневный визит (без БД).

Мини-игра: заходишь на сайт — забираешь монетки, серия дней подряд даёт
бонус. Механика намеренно копирует расчёт стрика привычек
(см. app/habits/streaks.py) — "чек-ин за день" структурно то же самое,
просто про сам факт визита, а не про конкретную привычку. Здесь не
переиспользуется current_streak напрямую только потому, что нужен не
только ТЕКУЩИЙ стрик, а стрик НА КАЖДЫЙ конкретный день истории (для
расчёта суммарных монет) — current_streak считает только "с конца".
"""

from datetime import date, timedelta

# 10 монет за сам факт визита + до +30 за серию (2 монеты за каждый день
# серии, но не больше 15 дней = 30 монет) — бонус растёт, но не
# бесконечно: иначе полугодовая серия давала бы абсурдные суммы, а сама
# цифра переставала бы восприниматься как награда за конкретный день.
_BASE_COINS = 10
_STREAK_BONUS_PER_DAY = 2
_STREAK_BONUS_CAP_DAYS = 15


def coins_for_streak_day(streak_including_today: int) -> int:
    """Монеты за один день с учётом серии НА ЭТОТ день (включая его)."""
    bonus_days = min(max(streak_including_today, 1), _STREAK_BONUS_CAP_DAYS)
    return _BASE_COINS + _STREAK_BONUS_PER_DAY * bonus_days


def total_coins(checked_days: set[date]) -> int:
    """Сумма наград по всем отмеченным дням.

    Каждый день учитывается с ЕГО СОБСТВЕННЫМ стриком на тот момент, а
    не текущим — иначе пропуск дня задним числом (или простое течение
    времени без визита) обнулял бы уже заработанные ранее монеты. Монеты
    — это история, а не индикатор текущей формы (для этого есть streak).
    """
    if not checked_days:
        return 0

    ordered = sorted(checked_days)
    total = 0
    streak = 0
    previous_day: date | None = None
    for day in ordered:
        if previous_day is not None and day == previous_day + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        total += coins_for_streak_day(streak)
        previous_day = day

    return total
