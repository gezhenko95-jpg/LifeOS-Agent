"""
Расчёт монет — чистые функции, без БД (см. app/rewards/coins.py).
"""

from datetime import date, timedelta

from app.rewards.coins import coins_for_streak_day, total_coins

TODAY = date.today()


def test_coins_for_streak_day_base_case():
    assert coins_for_streak_day(1) == 12  # 10 + 2*1


def test_coins_for_streak_day_grows_with_streak():
    assert coins_for_streak_day(5) == 20  # 10 + 2*5


def test_coins_for_streak_day_caps_at_fifteen_days():
    """Дальше 15 дней бонус не растёт — иначе полугодовая серия давала
    бы абсурдные суммы за один день."""
    assert coins_for_streak_day(15) == 40
    assert coins_for_streak_day(16) == 40
    assert coins_for_streak_day(1000) == 40


def test_coins_for_streak_day_treats_zero_as_one():
    """Формула вызывается только для дней, которые ЕСТЬ в истории —
    streak=0 сюда прийти не должен, но если придёт, не должна давать
    отрицательный/нулевой бонус."""
    assert coins_for_streak_day(0) == coins_for_streak_day(1)


def test_total_coins_empty_history():
    assert total_coins(set()) == 0


def test_total_coins_single_day():
    assert total_coins({TODAY}) == 12  # один день -> streak=1 -> 12


def test_total_coins_consecutive_days_use_growing_streak():
    """Три дня подряд: 1-й день streak=1 (12), 2-й streak=2 (14), 3-й
    streak=3 (16) — не "текущий стрик применяется ко всем дням"."""
    days = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)}

    assert total_coins(days) == 12 + 14 + 16


def test_total_coins_gap_resets_streak_but_not_earned_coins():
    """Пропуск дня НЕ отменяет уже заработанные монеты за прошлую
    серию — total_coins это история, а не индикатор текущей формы."""
    two_day_streak = {TODAY - timedelta(days=10), TODAY - timedelta(days=9)}
    single_far_day = {TODAY - timedelta(days=10)}

    with_gap = two_day_streak | {TODAY}  # разрыв между -9 и сегодня
    assert total_coins(with_gap) > total_coins(single_far_day)


def test_total_coins_is_order_independent():
    """Результат не должен зависеть от порядка дней во входном
    множестве (set и так не гарантирует порядок — считаем внутри по
    отсортированным датам)."""
    days_a = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=5)}
    days_b = set(reversed(sorted(days_a)))

    assert total_coins(days_a) == total_coins(days_b)
