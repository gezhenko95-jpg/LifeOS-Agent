"""
Интеграционный тест REST API памяти.

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


async def test_create_and_list_entry(client):
    response = await client.post(
        "/memory",
        json={"telegram_user_id": 1, "type": "fact", "content": "Живу в Москве"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Живу в Москве"
    assert body["type"] == "fact"
    assert body["archived"] is False

    response = await client.get("/memory", params={"telegram_user_id": 1})
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1


async def test_create_entry_with_blank_content_returns_400(client):
    response = await client.post(
        "/memory", json={"telegram_user_id": 1, "type": "fact", "content": "   "}
    )
    assert response.status_code == 400


async def test_search_by_query(client):
    await client.post(
        "/memory",
        json={"telegram_user_id": 5, "type": "preference", "content": "Люблю кофе"},
    )
    await client.post(
        "/memory",
        json={"telegram_user_id": 5, "type": "fact", "content": "Живу в Москве"},
    )

    response = await client.get("/memory", params={"telegram_user_id": 5, "q": "кофе"})

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["content"] == "Люблю кофе"


async def test_update_archives_entry_and_excludes_from_default_list(client):
    create_resp = await client.post(
        "/memory",
        json={"telegram_user_id": 6, "type": "goal", "content": "Выучить английский"},
    )
    entry_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/memory/{entry_id}",
        params={"telegram_user_id": 6},
        json={"archived": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["archived"] is True

    list_resp = await client.get("/memory", params={"telegram_user_id": 6})
    assert list_resp.json() == []


async def test_update_entry_wrong_owner_returns_404(client):
    create_resp = await client.post(
        "/memory",
        json={"telegram_user_id": 6, "type": "goal", "content": "Чужая запись"},
    )
    entry_id = create_resp.json()["id"]

    response = await client.patch(
        f"/memory/{entry_id}",
        params={"telegram_user_id": 999},
        json={"archived": True},
    )

    assert response.status_code == 404


async def test_get_context_returns_recent_entries(client):
    await client.post(
        "/memory",
        json={"telegram_user_id": 7, "type": "fact", "content": "Первая запись"},
    )
    await client.post(
        "/memory",
        json={"telegram_user_id": 7, "type": "fact", "content": "Вторая запись"},
    )

    response = await client.get(
        "/memory/context", params={"telegram_user_id": 7, "limit": 1}
    )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["content"] == "Вторая запись"


async def test_delete_entry(client):
    create_resp = await client.post(
        "/memory",
        json={"telegram_user_id": 8, "type": "journal", "content": "Хороший день"},
    )
    entry_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/memory/{entry_id}", params={"telegram_user_id": 8}
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get("/memory", params={"telegram_user_id": 8})
    assert list_resp.json() == []


async def test_update_nonexistent_entry_returns_404(client):
    response = await client.patch(
        "/memory/999999", params={"telegram_user_id": 1}, json={"archived": True}
    )

    assert response.status_code == 404


async def test_delete_nonexistent_entry_returns_404(client):
    response = await client.delete("/memory/999999", params={"telegram_user_id": 1})

    assert response.status_code == 404
