"""
Каталог магазина — константы (app/shop/catalog.py).

Проверяется не «правильность» цен (это решение владельца, не свойство
кода), а инварианты, на которые опирается остальной код: уникальность
id, известная категория, положительная цена.
"""

from app.shop.catalog import CATALOG, DECOR, KIND_TITLES, get_item


def test_item_ids_are_unique():
    ids = [item.id for item in CATALOG]

    assert len(ids) == len(set(ids))


def test_every_item_has_known_kind():
    assert all(item.kind in KIND_TITLES for item in CATALOG)


def test_every_price_is_positive():
    assert all(item.price > 0 for item in CATALOG)


def test_get_item_finds_by_id():
    item = get_item("seed_clover")

    assert item is not None
    assert item.price == 30


def test_get_item_returns_none_for_unknown():
    assert get_item("no_such_item") is None


def test_decorations_are_not_repeatable():
    """Второе такое же украшение питомцу надеть некуда — покупка разовая
    (на это опирается AlreadyOwnedError в сервисе)."""
    decor = [item for item in CATALOG if item.kind == DECOR]

    assert decor and all(not item.repeatable for item in decor)
