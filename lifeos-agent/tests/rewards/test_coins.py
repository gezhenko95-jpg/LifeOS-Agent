"""
Расчёт монет — чистые функции, без БД (см. app/rewards/coins.py).

Тесты на total_coins() и coins_for_streak_day() подавляют is_lucky_day
через monkeypatch (принудительно False), кроме тестов, посвящённых
именно удаче — иначе результат зависел бы от того, в какой день
реально запущен тест: is_lucky_day детерминирован ХЕШЕМ реальной даты,
а не константой, и это намеренно (см. докстринг), но делает тесты
"голой" формулы флейковыми без явного контроля этого фактора.
"""

from datetime import date, timedelta

import pytest

from app.rewards.coins import coins_for_streak_day, is_lucky_day, total_coins

TODAY = date.today()


@pytest.fixture(autouse=True)
def no_luck(monkeypatch):
    """По умолчанию во всех тестах этого файла удачи нет — она
    тестируется отдельно, ниже, с явным monkeypatch на True."""
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: False)


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


def test_coins_for_streak_day_lucky_doubles_it():
    assert coins_for_streak_day(1, lucky=True) == 24
    assert coins_for_streak_day(5, lucky=True) == 40


def test_total_coins_empty_history():
    assert total_coins(set(), telegram_user_id=1) == 0


def test_total_coins_single_day():
    assert total_coins({TODAY}, telegram_user_id=1) == 12  # streak=1 -> 12


def test_total_coins_consecutive_days_use_growing_streak():
    """Три дня подряд: 1-й день streak=1 (12), 2-й streak=2 (14), 3-й
    streak=3 (16) — не "текущий стрик применяется ко всем дням"."""
    days = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)}

    assert total_coins(days, telegram_user_id=1) == 12 + 14 + 16


def test_total_coins_gap_resets_streak_but_not_earned_coins():
    """Пропуск дня НЕ отменяет уже заработанные монеты за прошлую
    серию — total_coins это история, а не индикатор текущей формы."""
    two_day_streak = {TODAY - timedelta(days=10), TODAY - timedelta(days=9)}
    single_far_day = {TODAY - timedelta(days=10)}

    with_gap = two_day_streak | {TODAY}  # разрыв между -9 и сегодня
    assert total_coins(with_gap, 1) > total_coins(single_far_day, 1)


def test_total_coins_is_order_independent():
    """Результат не должен зависеть от порядка дней во входном
    множестве (set и так не гарантирует порядок — считаем внутри по
    отсортированным датам)."""
    days_a = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=5)}
    days_b = set(reversed(sorted(days_a)))

    assert total_coins(days_a, 1) == total_coins(days_b, 1)


# --- Удача: детерминизм и влияние на сумму (без no_luck из фикстуры) ---


def test_is_lucky_day_is_deterministic():
    """Один и тот же (пользователь, день) — всегда один и тот же
    результат: без этого total_coins "плавал" бы при каждом пересчёте
    истории, хотя пользователь ничего не делал (см. докстринг is_lucky_day)."""
    result_a = is_lucky_day(42, TODAY)
    result_b = is_lucky_day(42, TODAY)

    assert result_a == result_b


def test_is_lucky_day_differs_by_user_or_day():
    """Не константа "всегда true/false" — хотя бы для части входов даёт
    разные ответы (иначе это не удача, а фиксированный множитель)."""
    results = {is_lucky_day(uid, TODAY) for uid in range(200)}

    assert results == {True, False}


def test_is_lucky_day_roughly_matches_target_rate():
    """~15% дней удачные — не точная доля (это хеш, не генератор с
    заданной частотой), но должна быть в разумных пределах на большой
    выборке, а не, скажем, 60% или 1%."""
    sample_size = 2000
    lucky_count = sum(1 for uid in range(sample_size) if is_lucky_day(uid, TODAY))
    rate = lucky_count / sample_size

    assert 0.10 < rate < 0.20


def test_total_coins_doubles_when_day_is_lucky(monkeypatch):
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: True)

    assert total_coins({TODAY}, telegram_user_id=1) == 24  # 12 * 2
