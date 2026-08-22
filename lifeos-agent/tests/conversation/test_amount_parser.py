from app.conversation.amount_parser import extract_amount


def test_plain_integer():
    amount, remaining = extract_amount("потратил 1200 на продукты")

    assert amount == 1200
    assert remaining == "потратил на продукты"


def test_decimal_number_truncates_to_whole_rubles():
    amount, _ = extract_amount("1200.50 на что-то")

    assert amount == 1200


def test_decimal_with_comma():
    amount, _ = extract_amount("потратил 1200,50 на кофе")

    assert amount == 1200


def test_thousand_multiplier_short():
    amount, remaining = extract_amount("потратил 1.5к на подарок")

    assert amount == 1500
    assert remaining == "потратил на подарок"


def test_thousand_multiplier_word_full():
    amount, _ = extract_amount("потратил 2 тысячи на кино")

    assert amount == 2000


def test_thousand_multiplier_word_abbreviated():
    amount, _ = extract_amount("потратил 3 тыс. на одежду")

    assert amount == 3000


def test_currency_suffix_rub_word():
    amount, remaining = extract_amount("потратил 300 руб на кофе")

    assert amount == 300
    assert remaining == "потратил на кофе"


def test_currency_suffix_r_short():
    amount, _ = extract_amount("потратил 300р на кофе")

    assert amount == 300


def test_currency_suffix_ruble_sign():
    amount, _ = extract_amount("потратил 300₽ на кофе")

    assert amount == 300


def test_no_number_returns_none():
    amount, remaining = extract_amount("без суммы вообще")

    assert amount is None
    assert remaining == "без суммы вообще"


def test_zero_amount_returns_none():
    amount, remaining = extract_amount("потратил 0 на ничего")

    assert amount is None
    assert remaining == "потратил 0 на ничего"
