from datetime import date, datetime, timedelta

from app.conversation.date_parser import extract_due_date, extract_recurrence


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
