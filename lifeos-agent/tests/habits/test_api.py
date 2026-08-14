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

    complete_resp = await client.post(f"/habits/{habit_id}/complete")

    assert complete_resp.status_code == 200
    assert complete_resp.json()["streak"] == 1


async def test_complete_habit_is_idempotent_same_day(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 2, "title": "Спорт"}
    )
    habit_id = create_resp.json()["id"]

    await client.post(f"/habits/{habit_id}/complete")
    second_resp = await client.post(f"/habits/{habit_id}/complete")

    assert second_resp.json()["streak"] == 1


async def test_complete_nonexistent_habit_returns_404(client):
    response = await client.post("/habits/999999/complete")

    assert response.status_code == 404


async def test_delete_habit(client):
    create_resp = await client.post(
        "/habits", json={"telegram_user_id": 3, "title": "Дневник"}
    )
    habit_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/habits/{habit_id}")
    assert delete_resp.status_code == 204

    list_resp = await client.get("/habits", params={"telegram_user_id": 3})
    assert list_resp.json() == []


async def test_delete_nonexistent_habit_returns_404(client):
    response = await client.delete("/habits/999999")

    assert response.status_code == 404
