from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app.conversation.date_parser import extract_due_date, extract_recurrence


@contextmanager
def freeze_today(frozen: date):
    """Зафиксировать "сегодня" внутри date_parser.

    Подменяем не date целиком (тогда сломается конструирование дат), а
    подкласс с переопределённым today() — обычные вызовы date(y, m, d)
    продолжают работать.
    """

    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen

    with patch("app.conversation.date_parser.date", _FrozenDate):
        yield


def test_relative_minutes():
    before = datetime.now().astimezone()

    due, remaining = extract_due_date("Напомни через 2 минуты купить хлеб")

    assert due is not None
    delta = due - before
    assert timedelta(minutes=1, seconds=55) < delta < timedelta(minutes=2, seconds=5)
    assert remaining == "Напомни купить хлеб"


def test_relative_minutes_singular_and_plural_forms():
    due_one, _ = extract_due_date("через 1 минуту")
    due_five, _ = extract_due_date("через 5 минут")

    assert due_one is not None
    assert due_five is not None


def test_relative_hours():
    before = datetime.now().astimezone()

    due, remaining = extract_due_date("через 2 часа позвонить в банк")

    assert due is not None
    delta = due - before
    assert (
        timedelta(hours=1, minutes=59, seconds=55)
        < delta
        < timedelta(hours=2, seconds=5)
    )
    assert remaining == "позвонить в банк"


def test_time_of_day_later_today():
    now = datetime.now().astimezone()
    later = (now + timedelta(hours=1)).replace(second=0, microsecond=0)
    text = f"в {later.hour:02d}:{later.minute:02d} позвонить маме"

    due, remaining = extract_due_date(text)

    assert due is not None
    assert (due.hour, due.minute) == (later.hour, later.minute)
    assert due > now
    assert due - now < timedelta(hours=1, minutes=5)
    assert remaining == "позвонить маме"


def test_time_of_day_already_passed_becomes_next_occurrence():
    now = datetime.now().astimezone()
    earlier = (now - timedelta(hours=1)).replace(second=0, microsecond=0)
    text = f"в {earlier.hour:02d}:{earlier.minute:02d} позвонить маме"

    due, remaining = extract_due_date(text)

    assert due is not None
    assert (due.hour, due.minute) == (earlier.hour, earlier.minute)
    assert due > now
    # прошедшее сегодня время переносится на завтра, а не в недавнее прошлое
    assert due - now > timedelta(hours=22)
    assert remaining == "позвонить маме"


def test_no_date_returns_none_and_unchanged_text():
    due, remaining = extract_due_date("Купить молоко")

    assert due is None
    assert remaining == "Купить молоко"


def test_tomorrow():
    due, remaining = extract_due_date("Завтра купить молоко")

    assert due is not None
    assert due.date() == date.today() + timedelta(days=1)
    assert remaining == "купить молоко"


def test_today():
    due, remaining = extract_due_date("Сегодня позвонить маме")

    assert due.date() == date.today()
    assert remaining == "позвонить маме"


def test_day_after_tomorrow():
    due, remaining = extract_due_date("Послезавтра сдать отчет")

    assert due.date() == date.today() + timedelta(days=2)
    assert remaining == "сдать отчет"


def test_weekday_is_in_the_future_not_today():
    due, remaining = extract_due_date("В пятницу позвонить маме")

    assert due is not None
    assert due.weekday() == 4  # пятница
    assert due.date() > date.today()
    assert "пятниц" not in remaining.lower()


def test_numeric_date_without_year():
    due, remaining = extract_due_date("15.09 сходить к врачу")

    assert due.day == 15
    assert due.month == 9
    assert due.year == date.today().year
    assert remaining == "сходить к врачу"


def test_numeric_date_with_year():
    due, remaining = extract_due_date("01.01.2027 подвести итоги")

    assert (due.day, due.month, due.year) == (1, 1, 2027)
    assert remaining == "подвести итоги"


def test_invalid_numeric_date_is_ignored():
    due, remaining = extract_due_date("32.13 странная дата")

    assert due is None
    assert remaining == "32.13 странная дата"


def test_recurrence_daily():
    recurrence, remaining = extract_recurrence("каждый день пить воду")

    assert recurrence == "daily"
    assert remaining == "пить воду"


def test_recurrence_daily_alternate_form():
    recurrence, remaining = extract_recurrence("ежедневно проверять почту")

    assert recurrence == "daily"
    assert remaining == "проверять почту"


def test_recurrence_monthly():
    recurrence, remaining = extract_recurrence("каждый месяц оплатить аренду")

    assert recurrence == "monthly"
    assert remaining == "оплатить аренду"


def test_recurrence_weekly_generic():
    recurrence, remaining = extract_recurrence("каждую неделю делать уборку")

    assert recurrence == "weekly"
    assert remaining == "делать уборку"


def test_recurrence_weekday_substitutes_due_date_phrase():
    recurrence, remaining = extract_recurrence("каждый понедельник оплатить интернет")

    assert recurrence == "weekly"
    # "каждый понедельник" заменяется на "в понедельник" — чтобы
    # extract_due_date следующим шагом сам нашёл дату
    assert remaining == "в понедельник оплатить интернет"


def test_recurrence_weekday_then_due_date_finds_the_day():
    recurrence, without_recurrence = extract_recurrence(
        "каждый понедельник оплатить интернет"
    )
    due, remaining = extract_due_date(without_recurrence)

    assert recurrence == "weekly"
    assert due is not None
    assert due.weekday() == 0  # понедельник
    assert remaining == "оплатить интернет"


def test_no_recurrence_found():
    recurrence, remaining = extract_recurrence("купить молоко")

    assert recurrence is None
    assert remaining == "купить молоко"


# --- дд.мм без года не должно уезжать в прошлое (AUDIT.md, B-7) ---


def test_past_day_month_without_year_moves_to_next_year():
    """«встреча 05.01», написанная в декабре, означает январь будущего
    года. Иначе задача создаётся сразу просроченной и тут же стреляет
    напоминанием."""
    with freeze_today(date(2026, 12, 20)):
        due, remaining = extract_due_date("встреча 05.01")

    assert due.date() == date(2027, 1, 5)
    assert remaining == "встреча"


def test_future_day_month_stays_in_current_year():
    with freeze_today(date(2026, 8, 15)):
        due, _ = extract_due_date("оплатить 20.09")

    assert due.date() == date(2026, 9, 20)


def test_today_stays_today():
    """«созвон 15.08» утром 15 августа — это сегодня, а не через год."""
    with freeze_today(date(2026, 8, 15)):
        due, _ = extract_due_date("созвон 15.08")

    assert due.date() == date(2026, 8, 15)


def test_explicit_past_year_is_respected():
    """Явно указанный год не трогаем: это осознанное прошлое (отметить
    задним числом), догадываться не о чем."""
    with freeze_today(date(2026, 8, 15)):
        due, _ = extract_due_date("сдал отчёт 01.01.2020")

    assert due.date() == date(2020, 1, 1)


def test_leap_day_in_non_leap_year_rolls_to_next_leap_year():
    """29.02 не существует в 2027 — берём ближайший год, где существует."""
    with freeze_today(date(2027, 3, 5)):
        due, _ = extract_due_date("проверить 29.02")

    assert due.date() == date(2028, 2, 29)


def test_impossible_date_is_not_parsed():
    with freeze_today(date(2026, 8, 15)):
        due, remaining = extract_due_date("купить 45.99 чего-то")

    assert due is None
    assert remaining == "купить 45.99 чего-то"


# --- время суток в разных написаниях и количество словами ---


def test_time_with_space_separator():
    due, remaining = extract_due_date("позвонить в 19 00")

    assert (due.hour, due.minute) == (19, 0)
    assert remaining == "позвонить"


def test_time_with_dot_separator():
    due, _ = extract_due_date("позвонить в 19.30")

    assert (due.hour, due.minute) == (19, 30)


def test_bare_hour():
    due, remaining = extract_due_date("позвонить в 19")

    assert (due.hour, due.minute) == (19, 0)
    assert remaining == "позвонить"


def test_bare_hour_with_word():
    due, _ = extract_due_date("позвонить в 19 часов")

    assert (due.hour, due.minute) == (19, 0)


def test_bare_hour_does_not_eat_other_units():
    """«в 5 минутах ходьбы» — не время встречи, а часть названия."""
    due, remaining = extract_due_date("аптека в 5 минутах ходьбы")

    assert due is None
    assert remaining == "аптека в 5 минутах ходьбы"


def test_word_number_hours():
    before = datetime.now().astimezone()
    due, remaining = extract_due_date("через пару часов позвонить")

    assert (
        timedelta(hours=1, minutes=55) < (due - before) < timedelta(hours=2, minutes=5)
    )
    assert remaining == "позвонить"


def test_half_an_hour():
    before = datetime.now().astimezone()
    due, _ = extract_due_date("через полчаса выключить духовку")

    assert timedelta(minutes=25) < (due - before) < timedelta(minutes=35)


def test_one_hour_without_number():
    before = datetime.now().astimezone()
    due, _ = extract_due_date("через час выйти")

    assert timedelta(minutes=55) < (due - before) < timedelta(hours=1, minutes=5)


def test_invalid_hour_is_ignored():
    due, remaining = extract_due_date("купить в 45 магазине")

    assert due is None
    assert remaining == "купить в 45 магазине"


# --- день + время совмещаются (AUDIT.md, B-8) ---


def test_tomorrow_with_time_combines_both():
    """Раньше время выигрывало у дня: дата уезжала на сегодня, а слово
    «завтра» так и оставалось в названии задачи."""
    tomorrow = date.today() + timedelta(days=1)

    due, remaining = extract_due_date("завтра в 19:00 позвонить маме")

    assert due.date() == tomorrow
    assert (due.hour, due.minute) == (19, 0)
    assert remaining == "позвонить маме"


def test_today_with_time_combines_both():
    due, remaining = extract_due_date("сегодня в 23:30 забрать посылку")

    assert due.date() == date.today()
    assert (due.hour, due.minute) == (23, 30)
    assert remaining == "забрать посылку"


def test_day_after_tomorrow_with_bare_hour():
    due, remaining = extract_due_date("послезавтра в 8 бассейн")

    assert due.date() == date.today() + timedelta(days=2)
    assert (due.hour, due.minute) == (8, 0)
    assert remaining == "бассейн"


def test_weekday_with_time():
    due, remaining = extract_due_date("в пятницу в 15:30 встреча")

    assert due.weekday() == 4
    assert (due.hour, due.minute) == (15, 30)
    assert remaining == "встреча"


def test_numeric_date_with_time():
    due, remaining = extract_due_date("20.09 в 10:00 сдать отчёт")

    assert (due.month, due.day) == (9, 20)
    assert (due.hour, due.minute) == (10, 0)
    assert remaining == "сдать отчёт"


def test_day_without_time_keeps_default_hour():
    """Поведение по умолчанию не изменилось: дата без времени = 9 утра."""
    due, remaining = extract_due_date("завтра купить молоко")

    assert due.date() == date.today() + timedelta(days=1)
    assert (due.hour, due.minute) == (9, 0)
    assert remaining == "купить молоко"


# --- 12-часовая форма: «в 9 утра», «в 7 вечера» (живое использование) ---


def test_morning_hour():
    """«напомни сегодня в 9 утра запустить стиралку» — реальная фраза
    владельца: слово «утра» раньше оставалось в названии задачи."""
    due, remaining = extract_due_date("сегодня в 9 утра запустить стиралку")

    assert (due.hour, due.minute) == (9, 0)
    assert remaining == "запустить стиралку"


def test_evening_hour_shifts_to_pm():
    due, remaining = extract_due_date("в 7 вечера позвонить маме")

    assert (due.hour, due.minute) == (19, 0)
    assert remaining == "позвонить маме"


def test_afternoon_hour_shifts_to_pm():
    due, remaining = extract_due_date("в 3 дня забрать посылку")

    assert (due.hour, due.minute) == (15, 0)
    assert remaining == "забрать посылку"


def test_late_night_hour_shifts_to_pm():
    due, _ = extract_due_date("в 11 ночи выключить свет")

    assert (due.hour, due.minute) == (23, 0)


def test_early_night_hour_stays_am():
    """«в 2 ночи» это 02:00, а не 14:00 — граница по 4 часам."""
    due, _ = extract_due_date("в 2 ночи проверить сервер")

    assert (due.hour, due.minute) == (2, 0)


def test_noon_and_midnight_are_special_cases():
    """Двенадцать выбивается из правила «прибавить 12»."""
    noon, _ = extract_due_date("в 12 дня обед")
    midnight, _ = extract_due_date("в 12 ночи новый год")

    assert noon.hour == 12
    assert midnight.hour == 0


def test_day_part_with_minutes():
    due, remaining = extract_due_date("в 9:30 утра к врачу")

    assert (due.hour, due.minute) == (9, 30)
    assert remaining == "к врачу"
