"""
Интеграционный тест REST API фермы (по образцу tests/shop/test_api.py)
— монеты и семена зарабатываются/покупаются НАСТОЯЩИМИ /rewards и
/shop, ферма только тратит и растит.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import require_api_token
from app.db.base import Base
from app.db.session import get_session
from app.main import app


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
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: False)


async def _buy(client, user_id: int, item_id: str, times: int = 1):
    for _ in range(times):
        response = await client.post(
            "/shop/purchase", json={"telegram_user_id": user_id, "item_id": item_id}
        )
        assert response.status_code == 200, response.text


async def _earn_coins(client, user_id: int, monkeypatch, amount: int = 500):
    monkeypatch.setattr(
        "app.rewards.coins.coins_for_streak_day", lambda *a, **kw: amount
    )
    response = await client.post("/rewards/checkin", json={"telegram_user_id": user_id})
    assert response.status_code == 200


async def test_state_before_anything_is_empty(client):
    response = await client.get("/farm/state?telegram_user_id=1")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "available_seeds": 0,
        "available_fertilizer": 0,
        "available_rain": 0,
        "available_hay": 0,
        "plots": [],
    }


async def test_plant_without_seeds_returns_409(client):
    response = await client.post("/farm/plant", json={"telegram_user_id": 1})

    assert response.status_code == 409


async def test_buy_seed_then_plant_consumes_it(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")

    response = await client.post("/farm/plant", json={"telegram_user_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["available_seeds"] == 0
    assert len(body["plots"]) == 1
    assert body["plots"][0]["ready"] is False


async def test_plant_with_fertilizer_needs_booster(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")

    response = await client.post(
        "/farm/plant", json={"telegram_user_id": 1, "use_fertilizer": True}
    )

    assert response.status_code == 409


async def test_harvest_unready_plot_returns_409(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")
    state = (await client.post("/farm/plant", json={"telegram_user_id": 1})).json()
    plot_id = state["plots"][0]["id"]

    response = await client.post(
        f"/farm/plots/{plot_id}/harvest", json={"telegram_user_id": 1}
    )

    assert response.status_code == 409


async def test_harvest_unknown_plot_returns_404(client):
    response = await client.post(
        "/farm/plots/999/harvest", json={"telegram_user_id": 1}
    )

    assert response.status_code == 404


async def test_rain_without_booster_returns_409(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")
    await client.post("/farm/plant", json={"telegram_user_id": 1})

    response = await client.post("/farm/rain", json={"telegram_user_id": 1})

    assert response.status_code == 409


async def test_rain_reduces_ready_at(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")
    await _buy(client, 1, "booster_rain")
    before = (await client.post("/farm/plant", json={"telegram_user_id": 1})).json()[
        "plots"
    ][0]["ready_at"]

    response = await client.post("/farm/rain", json={"telegram_user_id": 1})

    assert response.status_code == 200
    after = response.json()["plots"][0]["ready_at"]
    assert after < before


async def test_farm_isolated_per_user(client, monkeypatch):
    await _earn_coins(client, 1, monkeypatch)
    await _buy(client, 1, "seed_clover")
    await client.post("/farm/plant", json={"telegram_user_id": 1})

    response = await client.get("/farm/state?telegram_user_id=2")

    body = response.json()
    assert body["available_seeds"] == 0
    assert body["plots"] == []
