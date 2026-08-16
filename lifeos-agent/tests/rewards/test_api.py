"""
Интеграционный тест REST API Rewards (по образцу tests/watchlist/test_api.py).
"""

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


async def test_status_before_any_checkin(client):
    response = await client.get("/rewards/status?telegram_user_id=1")

    assert response.status_code == 200
    body = response.json()
    assert body == {"claimed_today": False, "streak": 0, "total_coins": 0}


async def test_checkin_awards_coins(client):
    response = await client.post("/rewards/checkin", json={"telegram_user_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["claimed_today"] is True
    assert body["streak"] == 1
    assert body["total_coins"] == 12


async def test_checkin_twice_same_day_does_not_double_coins(client):
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    response = await client.post("/rewards/checkin", json={"telegram_user_id": 1})

    assert response.json()["total_coins"] == 12


async def test_status_after_checkin_reflects_it(client):
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    response = await client.get("/rewards/status?telegram_user_id=1")

    body = response.json()
    assert body["claimed_today"] is True
    assert body["total_coins"] == 12


async def test_checkins_isolated_per_user(client):
    await client.post("/rewards/checkin", json={"telegram_user_id": 1})
    response = await client.get("/rewards/status?telegram_user_id=2")

    assert response.json()["claimed_today"] is False
