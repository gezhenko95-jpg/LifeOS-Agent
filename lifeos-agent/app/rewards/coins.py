"""
Чистые функции начисления монеток за ежедневный визит (без БД).

Мини-игра: заходишь на сайт — забираешь монетки, серия дней подряд даёт
бонус, а некоторые дни — "счастливые" (x2). Механика намеренно копирует
расчёт стрика привычек (см. app/habits/streaks.py) — "чек-ин за день"
структурно то же самое, просто про сам факт визита, а не про конкретную
привычку. Здесь не переиспользуется current_streak напрямую только
потому, что нужен не только ТЕКУЩИЙ стрик, а стрик НА КАЖДЫЙ конкретный
день истории (для расчёта суммарных монет) — current_streak считает
только "с конца".
"""

import hashlib
from datetime import date, timedelta

# 10 монет за сам факт визита + до +30 за серию (2 монеты за каждый день
# серии, но не больше 15 дней = 30 монет) — бонус растёт, но не
# бесконечно: иначе полугодовая серия давала бы абсурдные суммы, а сама
# цифра переставала бы восприниматься как награда за конкретный день.
_BASE_COINS = 10
_STREAK_BONUS_PER_DAY = 2
_STREAK_BONUS_CAP_DAYS = 15

# Доля "счастливых" дней — x2 к награде. ~1 раз в неделю: достаточно
# редко, чтобы оставаться сюрпризом, достаточно часто, чтобы реально
# случаться, а не быть теоретической возможностью, которую никто не видит.
_LUCKY_DAY_CHANCE_PERCENT = 15
_LUCKY_DAY_MULTIPLIER = 2


def is_lucky_day(telegram_user_id: int, day: date) -> bool:
    """Детерминированная "случайность": да/нет однозначно определяется
    парой (пользователь, день) через хеш, а не генератором случайных
    чисел на каждый вызов.

    Это важно для честности игры: total_coins пересчитывается заново на
    КАЖДЫЙ запрос статуса из полной истории дней (см. total_coins) — будь
    удача настоящим random(), результат для одного и того же прошлого дня
    менялся бы при каждой перезагрузке страницы, и общая сумма монет
    "плавала" бы без всякого действия пользователя.
    """
    digest = hashlib.sha256(f"{telegram_user_id}:{day.isoformat()}".encode()).digest()
    # Первые два байта хеша -> число 0..65535 -> процент. Модульное
    # смещение от 65536%100 пренебрежимо мало для игровой механики.
    roll = int.from_bytes(digest[:2], "big") % 100
    return roll < _LUCKY_DAY_CHANCE_PERCENT


def coins_for_streak_day(streak_including_today: int, lucky: bool = False) -> int:
    """Монеты за один день с учётом серии НА ЭТОТ день (включая его) и
    того, счастливый ли это день."""
    bonus_days = min(max(streak_including_today, 1), _STREAK_BONUS_CAP_DAYS)
    base = _BASE_COINS + _STREAK_BONUS_PER_DAY * bonus_days
    return base * _LUCKY_DAY_MULTIPLIER if lucky else base


def total_coins(checked_days: set[date], telegram_user_id: int) -> int:
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
        total += coins_for_streak_day(streak, is_lucky_day(telegram_user_id, day))
        previous_day = day

    return total
