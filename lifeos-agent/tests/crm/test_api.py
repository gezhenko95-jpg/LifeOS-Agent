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


# --- Задачи контакта (отчёт владельца 24.08, вечер #6, волна 3) -------------


async def test_list_contact_tasks(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 7, "name": "Аня"}
    )
    contact_id = create_resp.json()["id"]
    await client.post(
        "/tasks",
        json={"telegram_user_id": 7, "title": "Позвонить", "contact_id": contact_id},
    )
    await client.post("/tasks", json={"telegram_user_id": 7, "title": "Без связи"})

    response = await client.get(
        f"/crm/contacts/{contact_id}/tasks", params={"telegram_user_id": 7}
    )

    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert titles == ["Позвонить"]


async def test_list_contact_tasks_empty(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 8, "name": "Боря"}
    )
    contact_id = create_resp.json()["id"]

    response = await client.get(
        f"/crm/contacts/{contact_id}/tasks", params={"telegram_user_id": 8}
    )

    assert response.status_code == 200
    assert response.json() == []


# --- Комментарии контакта ----------------------------------------------


async def test_add_and_list_contact_comments(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 9, "name": "Аня"}
    )
    contact_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/crm/contacts/{contact_id}/comments",
        json={"telegram_user_id": 9, "text": "Любит подарки на праздники"},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["text"] == "Любит подарки на праздники"

    list_resp = await client.get(
        f"/crm/contacts/{contact_id}/comments", params={"telegram_user_id": 9}
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    contacts_resp = await client.get("/crm/contacts", params={"telegram_user_id": 9})
    assert contacts_resp.json()[0]["comment_count"] == 1


async def test_add_comment_missing_contact_returns_404(client):
    response = await client.post(
        "/crm/contacts/9999/comments",
        json={"telegram_user_id": 9, "text": "X"},
    )
    assert response.status_code == 404


async def test_delete_contact_comment(client):
    create_resp = await client.post(
        "/crm/contacts", json={"telegram_user_id": 10, "name": "Аня"}
    )
    contact_id = create_resp.json()["id"]
    add_resp = await client.post(
        f"/crm/contacts/{contact_id}/comments",
        json={"telegram_user_id": 10, "text": "X"},
    )
    comment_id = add_resp.json()["id"]

    delete_resp = await client.delete(
        f"/crm/comments/{comment_id}", params={"telegram_user_id": 10}
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get(
        f"/crm/contacts/{contact_id}/comments", params={"telegram_user_id": 10}
    )
    assert list_resp.json() == []


async def test_delete_missing_comment_returns_404(client):
    response = await client.delete(
        "/crm/comments/9999", params={"telegram_user_id": 10}
    )
    assert response.status_code == 404
