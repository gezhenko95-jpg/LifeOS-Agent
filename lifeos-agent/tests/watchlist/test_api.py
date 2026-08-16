"""
Интеграционный тест REST API Watchlist (по образцу tests/habits/test_api.py).
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


async def test_create_and_list_item(client):
    response = await client.post(
        "/watchlist",
        json={"telegram_user_id": 1, "title": "Дюна", "media_type": "movie"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Дюна"
    assert body["status"] == "to_watch"

    response = await client.get("/watchlist", params={"telegram_user_id": 1})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1


async def test_create_item_with_blank_title_returns_400(client):
    response = await client.post(
        "/watchlist", json={"telegram_user_id": 1, "title": "   "}
    )
    assert response.status_code == 400


async def test_create_item_with_invalid_media_type_returns_400(client):
    response = await client.post(
        "/watchlist",
        json={"telegram_user_id": 1, "title": "X", "media_type": "podcast"},
    )
    assert response.status_code == 400


async def test_list_includes_both_statuses(client):
    create_resp = await client.post(
        "/watchlist", json={"telegram_user_id": 2, "title": "Дюна"}
    )
    item_id = create_resp.json()["id"]
    await client.post(f"/watchlist/{item_id}/complete", params={"telegram_user_id": 2})
    await client.post("/watchlist", json={"telegram_user_id": 2, "title": "1984"})

    response = await client.get("/watchlist", params={"telegram_user_id": 2})

    statuses = {item["status"] for item in response.json()}
    assert statuses == {"to_watch", "done"}


async def test_complete_item(client):
    create_resp = await client.post(
        "/watchlist", json={"telegram_user_id": 3, "title": "Дюна"}
    )
    item_id = create_resp.json()["id"]

    complete_resp = await client.post(
        f"/watchlist/{item_id}/complete", params={"telegram_user_id": 3}
    )

    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "done"


async def test_complete_nonexistent_item_returns_404(client):
    response = await client.post(
        "/watchlist/999999/complete", params={"telegram_user_id": 1}
    )

    assert response.status_code == 404


async def test_complete_item_wrong_owner_returns_404(client):
    create_resp = await client.post(
        "/watchlist", json={"telegram_user_id": 3, "title": "Дюна"}
    )
    item_id = create_resp.json()["id"]

    response = await client.post(
        f"/watchlist/{item_id}/complete", params={"telegram_user_id": 999}
    )

    assert response.status_code == 404


async def test_delete_item(client):
    create_resp = await client.post(
        "/watchlist", json={"telegram_user_id": 4, "title": "Дюна"}
    )
    item_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/watchlist/{item_id}", params={"telegram_user_id": 4}
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get("/watchlist", params={"telegram_user_id": 4})
    assert list_resp.json() == []


async def test_delete_nonexistent_item_returns_404(client):
    response = await client.delete("/watchlist/999999", params={"telegram_user_id": 1})

    assert response.status_code == 404
