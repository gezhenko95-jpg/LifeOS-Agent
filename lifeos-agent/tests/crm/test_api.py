"""
Интеграционный тест REST API личного CRM.

Не было ни одного — контакты проверялись только на уровне сервиса
(tests/crm/test_service.py) и репозитория. Роутов было три (создать/
список/отметить/удалить), теперь плюс PATCH (specs/018, довесок:
notes/tags/nudge_after_days раньше некуда было менять после создания).
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


async def test_create_and_list_contact(client):
    response = await client.post(
        "/crm/contacts", json={"telegram_user_id": 1, "name": "Аня"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Аня"

    response = await client.get("/crm/contacts", params={"telegram_user_id": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_contact_with_tags_and_nudge_after_days(client):
    response = await client.post(
        "/crm/contacts",
        json={
            "telegram_user_id": 1,
            "name": "Аня",
            "tags": "работа",
            "nudge_after_days": 10,
        },
    )
    assert response.status_code == 201
    assert response.json()["tags"] == "работа"
    assert response.json()["nudge_after_days"] == 10


async def test_update_contact_notes(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 2, "name": "Боря"}
    )
    contact_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/crm/contacts/{contact_id}",
        params={"telegram_user_id": 2},
        json={"notes": "Любит кофе"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["notes"] == "Любит кофе"


async def test_update_contact_clear_nudge_after_days(client):
    create_resp = await client.post(
        "/crm/contacts",
        json={"telegram_user_id": 2, "name": "Боря", "nudge_after_days": 5},
    )
    contact_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/crm/contacts/{contact_id}",
        params={"telegram_user_id": 2},
        json={"clear_nudge_after_days": True},
    )
    assert patch_resp.json()["nudge_after_days"] is None


async def test_update_missing_contact_returns_404(client):
    response = await client.patch(
        "/crm/contacts/9999",
        params={"telegram_user_id": 2},
        json={"notes": "X"},
    )
    assert response.status_code == 404


async def test_update_someone_elses_contact_returns_404(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 3, "name": "Чужой"}
    )
    contact_id = create_resp.json()["id"]

    response = await client.patch(
        f"/crm/contacts/{contact_id}",
        params={"telegram_user_id": 4},
        json={"notes": "X"},
    )
    assert response.status_code == 404


async def test_mark_contacted(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 5, "name": "Аня"}
    )
    contact_id = create_resp.json()["id"]

    response = await client.post(
        f"/crm/contacts/{contact_id}/contacted", params={"telegram_user_id": 5}
    )
    assert response.status_code == 200


async def test_delete_contact(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 6, "name": "Аня"}
    )
    contact_id = create_resp.json()["id"]

    response = await client.delete(
        f"/crm/contacts/{contact_id}", params={"telegram_user_id": 6}
    )
    assert response.status_code == 204

    list_resp = await client.get("/crm/contacts", params={"telegram_user_id": 6})
    assert list_resp.json() == []
