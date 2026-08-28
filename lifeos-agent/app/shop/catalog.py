"""
Каталог товаров магазина — константы, а не таблица в БД.

Тот же приём, что у персонажей ассистента (app/assistant/personas.py):
пока ассортимент правится только разработчиком вместе с кодом, который
знает про эффект каждого товара, отдельная таблица и CRUD к ней были бы
инфраструктурой без пользователя. Появится нужда менять ассортимент на
лету — каталог переедет в БД, покупки от этого не пострадают: в
coin_transactions лежит item_id строкой, а не внешним ключом.

Цены откалиброваны по реальной выдаче чек-ина (app/rewards/coins.py):
12 монет в первый день, до 40 при длинной серии, в среднем ~30 в день.
Отсюда решение владельца (26.08): семя = 30 монет, то есть один день
визитов = одна грядка. Всё остальное расставлено относительно этой
единицы: ускоритель — меньше семени (помогает, но не заменяет),
украшения — от двух дней (шляпа) до недели с лишним (корона).
"""

from dataclasses import dataclass

# Категории. Разделены не ради красоты вывода: у них разное поведение
# при повторной покупке (см. repeatable ниже) и разные потребители —
# семена и ускорители расходует ферма, украшения носит питомец, заморозку
# — привычки (app/habits/).
SEED = "seed"
BOOSTER = "booster"
DECOR = "decor"
FREEZE = "freeze"

KIND_TITLES = {
    SEED: "Семена",
    BOOSTER: "Ускорители фермы",
    DECOR: "Украшения питомца",
    FREEZE: "Стрики",
}


@dataclass(frozen=True)
class ShopItem:
    id: str
    kind: str
    title: str
    emoji: str
    price: int
    description: str
    # Расходуемое (семена, ускорители) покупается сколько угодно раз и
    # копится количеством. Украшение — разовое: второй такой же цилиндр
    # питомцу надеть некуда, и списывать за него монеты нечестно.
    repeatable: bool


CATALOG: tuple[ShopItem, ...] = (
    ShopItem(
        id="seed_clover",
        kind=SEED,
        title="Семена клевера",
        emoji="🍀",
        price=30,
        description="Грядка растёт сутки и даёт 10 сена",
        repeatable=True,
    ),
    ShopItem(
        id="booster_fertilizer",
        kind=BOOSTER,
        title="Удобрение",
        emoji="🌾",
        price=45,
        description="Грядка созревает вдвое быстрее",
        repeatable=True,
    ),
    ShopItem(
        id="booster_rain",
        kind=BOOSTER,
        title="Тёплый дождь",
        emoji="🌧",
        price=25,
        description="Минус 6 часов до сбора на всех грядках",
        repeatable=True,
    ),
    ShopItem(
        id="decor_hat",
        kind=DECOR,
        title="Цилиндр",
        emoji="🎩",
        price=60,
        description="Питомец при параде",
        repeatable=False,
    ),
    ShopItem(
        id="decor_scarf",
        kind=DECOR,
        title="Шарф",
        emoji="🧣",
        price=80,
        description="Тёплый, полосатый",
        repeatable=False,
    ),
    ShopItem(
        id="decor_glasses",
        kind=DECOR,
        title="Очки",
        emoji="🕶",
        price=120,
        description="Питомец делает вид, что всё под контролем",
        repeatable=False,
    ),
    ShopItem(
        id="decor_crown",
        kind=DECOR,
        title="Корона",
        emoji="👑",
        price=250,
        description="Больше недели визитов — и питомец коронован",
        repeatable=False,
    ),
    ShopItem(
        id="streak_freeze",
        kind=FREEZE,
        title="Заморозка стрика",
        emoji="🧊",
        price=40,
        description="Защищает серию привычки от одного пропущенного дня",
        repeatable=True,
    ),
)

_BY_ID = {item.id: item for item in CATALOG}


def get_item(item_id: str) -> ShopItem | None:
    return _BY_ID.get(item_id)
