"""
Интеграционный тест REST API задач.

Использует SQLite в памяти (aiosqlite) вместо Postgres, чтобы тесты
не требовали поднятого Docker/БД. В проде используется asyncpg/Postgres.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_create_and_list_task(client):
    response = await client.post(
        "/tasks", json={"telegram_user_id": 1, "title": "Купить молоко"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Купить молоко"
    assert body["status"] == "active"

    response = await client.get("/tasks", params={"telegram_user_id": 1})
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Купить молоко"


async def test_create_task_with_blank_title_returns_400(client):
    response = await client.post("/tasks", json={"telegram_user_id": 1, "title": "   "})
    # min_length=1 пропускает пробелы дальше — пустоту после strip() отбраковывает сервис
    assert response.status_code == 400


async def test_create_task_with_empty_title_returns_422(client):
    response = await client.post("/tasks", json={"telegram_user_id": 1, "title": ""})
    # пустая строка отбрасывается Pydantic (min_length=1) еще до сервиса
    assert response.status_code == 422


async def test_complete_and_delete_task(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 2, "title": "Позвонить маме"}
    )
    task_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/tasks/{task_id}", json={"status": "completed"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "completed"

    delete_resp = await client.delete(f"/tasks/{task_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get("/tasks", params={"telegram_user_id": 2})
    assert get_resp.json() == []


async def test_create_task_with_priority_and_sorting(client):
    await client.post("/tasks", json={"telegram_user_id": 3, "title": "Обычная"})
    high_resp = await client.post(
        "/tasks",
        json={"telegram_user_id": 3, "title": "Важная", "priority": "high"},
    )
    assert high_resp.status_code == 201
    assert high_resp.json()["priority"] == "high"

    list_resp = await client.get("/tasks", params={"telegram_user_id": 3})
    titles = [task["title"] for task in list_resp.json()]
    assert titles == ["Важная", "Обычная"]


async def test_create_task_with_invalid_priority_returns_400(client):
    response = await client.post(
        "/tasks",
        json={"telegram_user_id": 3, "title": "X", "priority": "urgent"},
    )

    assert response.status_code == 400


async def test_update_task_priority(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 4, "title": "X"}
    )
    task_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/tasks/{task_id}", json={"priority": "low"})

    assert patch_resp.status_code == 200
    assert patch_resp.json()["priority"] == "low"


async def test_update_nonexistent_task_returns_404(client):
    response = await client.patch("/tasks/999999", json={"status": "completed"})

    assert response.status_code == 404


async def test_delete_nonexistent_task_returns_404(client):
    response = await client.delete("/tasks/999999")

    assert response.status_code == 404
