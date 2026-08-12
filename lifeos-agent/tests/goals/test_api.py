"""
Интеграционный тест REST API целей.

Использует SQLite в памяти (aiosqlite), как tests/tasks/test_api.py.
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


async def test_create_and_list_goal(client):
    response = await client.post(
        "/goals", json={"telegram_user_id": 1, "title": "Выучить английский"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Выучить английский"
    assert body["progress"] == 0
    assert body["status"] == "active"

    response = await client.get("/goals", params={"telegram_user_id": 1})
    assert response.status_code == 200
    goals = response.json()
    assert len(goals) == 1


async def test_create_goal_with_blank_title_returns_400(client):
    response = await client.post("/goals", json={"telegram_user_id": 1, "title": "   "})
    assert response.status_code == 400


async def test_update_goal_progress(client):
    create_resp = await client.post(
        "/goals", json={"telegram_user_id": 2, "title": "Марафон"}
    )
    goal_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/goals/{goal_id}", json={"progress": 40})

    assert patch_resp.status_code == 200
    assert patch_resp.json()["progress"] == 40


async def test_update_goal_progress_out_of_range_returns_400(client):
    create_resp = await client.post(
        "/goals", json={"telegram_user_id": 2, "title": "Марафон"}
    )
    goal_id = create_resp.json()["id"]

    response = await client.patch(f"/goals/{goal_id}", json={"progress": 150})

    assert response.status_code == 422


async def test_complete_goal_via_status_update(client):
    create_resp = await client.post(
        "/goals", json={"telegram_user_id": 3, "title": "Дочитать книгу"}
    )
    goal_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/goals/{goal_id}", json={"status": "completed"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "completed"

    list_resp = await client.get("/goals", params={"telegram_user_id": 3})
    assert list_resp.json() == []


async def test_delete_goal(client):
    create_resp = await client.post(
        "/goals", json={"telegram_user_id": 4, "title": "X"}
    )
    goal_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/goals/{goal_id}")
    assert delete_resp.status_code == 204

    list_resp = await client.get("/goals", params={"telegram_user_id": 4})
    assert list_resp.json() == []


async def test_update_nonexistent_goal_returns_404(client):
    response = await client.patch("/goals/999999", json={"progress": 10})

    assert response.status_code == 404


async def test_delete_nonexistent_goal_returns_404(client):
    response = await client.delete("/goals/999999")

    assert response.status_code == 404
