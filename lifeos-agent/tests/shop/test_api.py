"""
Интеграционный тест REST API магазина (по образцу
tests/rewards/test_api.py) — здесь, в отличие от tests/shop/test_service,
монеты зарабатываются НАСТОЯЩИМ чек-ином через /rewards/checkin: связка
двух доменов (заработок в rewards, трата в shop) — самое ценное, что
проверяет этот файл.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import require_api_token
from app.db.base import Base
from app.db.session import get_session
from app.main import app

# Первый день серии без удачи — ровно столько даёт чек-ин
# (app/rewards/coins.py), на этом числе построены проверки ниже.
FIRST_DAY_COINS = 12


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_api_token] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture(autouse=True)
def no_luck(monkeypatch):
    """Тот же приём, что в tests/rewards/test_api.py: сегодняшний день
    для пользователя 1 по-настоящему может выпасть «счастливым», и тогда
    монет было бы вдвое больше, чем ждут проверки."""
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: False)


async def test_state_before_any_checkin_is_empty_wallet(client):
    response = await client.get("/shop/state?telegram_user_id=1")

    assert response.status_code == 200
    body = response.json()
    assert body["earned_coins"] == 0
    assert body["spent_coins"] == 0
    assert body["balance"] == 0
    assert all(item["owned"] == 0 for item in body["items"])
    assert all(item["affordable"] is False for item in body["items"])


async def test_catalog_items_carry_display_fields(client):
    body = (await client.get("/shop/state?telegram_user_id=1")).json()

    clover = next(item for item in body["items"] if item["id"] == "seed_clover")
    assert clover["price"] == 30
    assert clover["kind_title"] == "Семена"
    assert clover["repeatable"] is True
    assert clover["emoji"]
    assert clover["description"]


async def test_checkin_coins_become_shop_balance(client):
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})

    body = (await client.get("/shop/state?telegram_user_id=1")).json()

    assert body["earned_coins"] == FIRST_DAY_COINS
    assert body["balance"] == FIRST_DAY_COINS


async def test_purchase_without_enough_coins_returns_409(client):
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})

    response = await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "seed_clover"}
    )

    assert response.status_code == 409


async def test_purchase_of_unknown_item_returns_404(client):
    response = await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "no_such_item"}
    )

    assert response.status_code == 404


async def test_purchase_spends_coins_and_returns_new_state(client, monkeypatch):
    # Хватает на «Тёплый дождь» (25) — вместо трёх дней ожидания
    # подменяем выдачу чек-ина одним щедрым днём.
    monkeypatch.setattr("app.rewards.coins.coins_for_streak_day", lambda *a, **kw: 100)
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})

    response = await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "booster_rain"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["earned_coins"] == 100
    assert body["spent_coins"] == 25
    assert body["balance"] == 75
    rain = next(item for item in body["items"] if item["id"] == "booster_rain")
    assert rain["owned"] == 1


async def test_purchase_does_not_change_rewards_status(client, monkeypatch):
    """Заработанное за всё время не трогается покупкой — /rewards/status
    после траты отдаёт ровно то же число (вариант (A) спеки 028)."""
    monkeypatch.setattr("app.rewards.coins.coins_for_streak_day", lambda *a, **kw: 100)
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "booster_rain"}
    )

    body = (await client.get("/rewards/status?telegram_user_id=1")).json()

    assert body["total_coins"] == 100


async def test_second_purchase_of_decoration_returns_409(client, monkeypatch):
    monkeypatch.setattr("app.rewards.coins.coins_for_streak_day", lambda *a, **kw: 500)
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "decor_hat"}
    )

    response = await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "decor_hat"}
    )

    assert response.status_code == 409


async def test_purchases_isolated_per_user(client, monkeypatch):
    monkeypatch.setattr("app.rewards.coins.coins_for_streak_day", lambda *a, **kw: 500)
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    await client.post(
        "/shop/purchase", json={"telegram_user_id": 1, "item_id": "decor_hat"}
    )

    body = (await client.get("/shop/state?telegram_user_id=2")).json()

    assert body["balance"] == 0
    assert all(item["owned"] == 0 for item in body["items"])
