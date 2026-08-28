"""
Интеграционный тест REST API привычек.

Использует SQLite в памяти (aiosqlite), как tests/tasks/test_api.py.
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
    # Аутентификация REST API проверяется отдельно
    # (tests/api/test_auth.py) — здесь тестируется поведение
    # эндпоинтов, а не замок на двери.
    app.dependency_overrides[require_api_token] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_create_and_list_habit(client):
    response = await client.post(
        "/habits", json={"telegram_user_id": 1, "title": "Читать"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Читать"
    assert body["streak"] == 0

    response = await client.get("/habits", params={"telegram_user_id": 1})
    assert response.status_code == 200
    habits = response.json()
    assert len(habits) == 1


async def test_create_habit_with_blank_title_returns_400(client):
    response = await client.post(
        "/habits", json={"telegram_user_id": 1, "title": "   "}
    )
    assert response.status_code == 400


async def test_complete_habit_increments_streak(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 2, "title": "Спорт"}
    )
    habit_id = create_resp.json()["id"]

    complete_resp = await client.post(
        f"/habits/{habit_id}/complete", params={"telegram_user_id": 2}
    )

    assert complete_resp.status_code == 200
    assert complete_resp.json()["streak"] == 1


async def test_complete_habit_is_idempotent_same_day(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 2, "title": "Спорт"}
    )
    habit_id = create_resp.json()["id"]

    await client.post(f"/habits/{habit_id}/complete", params={"telegram_user_id": 2})
    second_resp = await client.post(
        f"/habits/{habit_id}/complete", params={"telegram_user_id": 2}
    )

    assert second_resp.json()["streak"] == 1


async def test_complete_nonexistent_habit_returns_404(client):
    response = await client.post(
        "/habits/999999/complete", params={"telegram_user_id": 1}
    )

    assert response.status_code == 404


async def test_complete_habit_wrong_owner_returns_404(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 2, "title": "Спорт"}
    )
    habit_id = create_resp.json()["id"]

    response = await client.post(
        f"/habits/{habit_id}/complete", params={"telegram_user_id": 999}
    )

    assert response.status_code == 404


async def test_delete_habit(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 3, "title": "Дневник"}
    )
    habit_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/habits/{habit_id}", params={"telegram_user_id": 3}
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get("/habits", params={"telegram_user_id": 3})
    assert list_resp.json() == []


async def test_delete_nonexistent_habit_returns_404(client):
    response = await client.delete("/habits/999999", params={"telegram_user_id": 1})

    assert response.status_code == 404


# --- Стрик-заморозка (specs/029) ----------------------------------------


async def test_streak_freeze_wallet_starts_at_zero(client):
    response = await client.get(
        "/habits/streak-freezes", params={"telegram_user_id": 10}
    )
    assert response.status_code == 200
    assert response.json() == {"available": 0}


async def test_use_streak_freeze_without_inventory_returns_409(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 10, "title": "Читать"}
    )
    habit_id = create_resp.json()["id"]

    response = await client.post(
        f"/habits/{habit_id}/streak-freeze", params={"telegram_user_id": 10}
    )
    assert response.status_code == 409


async def test_use_streak_freeze_missing_habit_returns_404(client):
    response = await client.post(
        "/habits/999999/streak-freeze", params={"telegram_user_id": 10}
    )
    assert response.status_code == 404


async def test_streak_freeze_wallet_reflects_purchase(client, monkeypatch):
    # Тот же приём, что tests/shop/test_api.py: делаем чек-ин
    # детерминированным, чтобы монет хватило на покупку (40 за заморозку).
    monkeypatch.setattr("app.rewards.coins.is_lucky_day", lambda *a, **kw: False)
    monkeypatch.setattr("app.rewards.coins.coins_for_streak_day", lambda *a, **kw: 100)
    await client.post("/rewards/checkin", json={"telegram_user_id": 11})

    await client.post(
        "/shop/purchase",
        json={"telegram_user_id": 11, "item_id": "streak_freeze"},
    )

    response = await client.get(
        "/habits/streak-freezes", params={"telegram_user_id": 11}
    )
    assert response.json() == {"available": 1}
