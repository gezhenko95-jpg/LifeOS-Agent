from app.conversation.birthday_parser import extract_birthday


def test_plain_date():
    month, day, remaining = extract_birthday("Аня 14.09")

    assert (month, day) == (9, 14)
    assert remaining == "Аня"


def test_date_with_year_is_extracted_but_year_discarded():
    month, day, remaining = extract_birthday("Петя 14.09.1990")

    assert (month, day) == (9, 14)
    assert remaining == "Петя"


def test_no_date_returns_none():
    month, day, remaining = extract_birthday("Просто Аня")

    assert (month, day) == (None, None)
    assert remaining == "Просто Аня"


def test_impossible_date_returns_none():
    month, day, remaining = extract_birthday("Аня 31.02")

    assert (month, day) == (None, None)
    assert remaining == "Аня 31.02"


def test_leap_day_is_accepted():
    month, day, _ = extract_birthday("Аня 29.02")

    assert (month, day) == (2, 29)


def test_date_after_name():
    month, day, remaining = extract_birthday("Аня 14.09 подруга детства")

    assert (month, day) == (9, 14)
    assert remaining == "Аня подруга детства"
