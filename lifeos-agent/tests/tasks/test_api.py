"""
Интеграционный тест REST API задач.

Использует SQLite в памяти (aiosqlite) вместо Postgres, чтобы тесты
не требовали поднятого Docker/БД. В проде используется asyncpg/Postgres.
"""

from datetime import datetime

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

    patch_resp = await client.patch(
        f"/tasks/{task_id}",
        params={"telegram_user_id": 2},
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "completed"

    delete_resp = await client.delete(
        f"/tasks/{task_id}", params={"telegram_user_id": 2}
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get("/tasks", params={"telegram_user_id": 2})
    assert get_resp.json() == []


async def test_update_task_wrong_owner_returns_404(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 2, "title": "Чужая задача"}
    )
    task_id = create_resp.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        params={"telegram_user_id": 999},
        json={"status": "completed"},
    )

    assert response.status_code == 404


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

    patch_resp = await client.patch(
        f"/tasks/{task_id}", params={"telegram_user_id": 4}, json={"priority": "low"}
    )

    assert patch_resp.status_code == 200
    assert patch_resp.json()["priority"] == "low"


async def test_update_nonexistent_task_returns_404(client):
    response = await client.patch(
        "/tasks/999999",
        params={"telegram_user_id": 1},
        json={"status": "completed"},
    )

    assert response.status_code == 404


async def test_delete_nonexistent_task_returns_404(client):
    response = await client.delete("/tasks/999999", params={"telegram_user_id": 1})

    assert response.status_code == 404


async def test_create_recurring_task_returns_recurrence(client):
    response = await client.post(
        "/tasks",
        json={
            "telegram_user_id": 5,
            "title": "Оплатить интернет",
            "due_date": "2026-08-17T09:00:00Z",
            "recurrence": "weekly",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recurrence"] == "weekly"
    assert body["due_date"] is not None


async def test_completing_recurring_task_creates_next_occurrence(client):
    create_resp = await client.post(
        "/tasks",
        json={
            "telegram_user_id": 6,
            "title": "Пить воду",
            "due_date": "2026-08-13T09:00:00Z",
            "recurrence": "daily",
        },
    )
    task_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/tasks/{task_id}",
        params={"telegram_user_id": 6},
        json={"status": "completed"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["completed_at"] is not None

    list_resp = await client.get("/tasks", params={"telegram_user_id": 6})
    active_tasks = list_resp.json()
    assert len(active_tasks) == 1
    assert active_tasks[0]["title"] == "Пить воду"
    next_due = datetime.fromisoformat(active_tasks[0]["due_date"])
    assert (next_due.year, next_due.month, next_due.day) == (2026, 8, 14)


async def test_stats_counts_completed_this_week(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 7, "title": "Отчёт"}
    )
    task_id = create_resp.json()["id"]
    await client.patch(
        f"/tasks/{task_id}",
        params={"telegram_user_id": 7},
        json={"status": "completed"},
    )

    response = await client.get("/tasks/stats", params={"telegram_user_id": 7})

    assert response.status_code == 200
    assert response.json()["completed_this_week"] == 1


async def test_stats_zero_when_nothing_completed(client):
    response = await client.get("/tasks/stats", params={"telegram_user_id": 8})

    assert response.status_code == 200
    assert response.json()["completed_this_week"] == 0


# --- Подзадачи/эпики (specs/022-tasks-v2.md) --------------------------------


async def test_create_subtask_and_list_it(client):
    parent = await client.post("/tasks", json={"telegram_user_id": 10, "title": "Эпик"})
    parent_id = parent.json()["id"]

    child = await client.post(
        "/tasks",
        json={"telegram_user_id": 10, "title": "Подзадача", "parent_id": parent_id},
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent_id

    subtasks = await client.get(
        f"/tasks/{parent_id}/subtasks", params={"telegram_user_id": 10}
    )
    assert subtasks.status_code == 200
    assert len(subtasks.json()) == 1
    assert subtasks.json()[0]["title"] == "Подзадача"


async def test_subtasks_excluded_from_top_level_list_but_counted(client):
    parent = await client.post("/tasks", json={"telegram_user_id": 11, "title": "Эпик"})
    parent_id = parent.json()["id"]
    await client.post(
        "/tasks",
        json={"telegram_user_id": 11, "title": "Подзадача", "parent_id": parent_id},
    )

    tasks = await client.get("/tasks", params={"telegram_user_id": 11})

    assert len(tasks.json()) == 1
    assert tasks.json()[0]["id"] == parent_id
    assert tasks.json()[0]["subtask_count"] == 1


async def test_create_task_with_unknown_parent_returns_400(client):
    response = await client.post(
        "/tasks",
        json={"telegram_user_id": 12, "title": "Подзадача", "parent_id": 9999},
    )
    assert response.status_code == 400


# --- "В работе" --------------------------------------------------------


async def test_toggle_in_progress(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 13, "title": "Задача"}
    )
    task_id = create_resp.json()["id"]
    assert create_resp.json()["in_progress"] is False

    on = await client.post(
        f"/tasks/{task_id}/in-progress", params={"telegram_user_id": 13}
    )
    assert on.status_code == 200
    assert on.json()["in_progress"] is True

    off = await client.post(
        f"/tasks/{task_id}/in-progress", params={"telegram_user_id": 13}
    )
    assert off.json()["in_progress"] is False


async def test_toggle_in_progress_missing_task_returns_404(client):
    response = await client.post(
        "/tasks/9999/in-progress", params={"telegram_user_id": 13}
    )
    assert response.status_code == 404


# --- Комментарии ---------------------------------------------------------


async def test_add_and_list_comments(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 14, "title": "Задача"}
    )
    task_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/tasks/{task_id}/comments",
        json={"telegram_user_id": 14, "text": "Начал работать"},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["text"] == "Начал работать"

    list_resp = await client.get(
        f"/tasks/{task_id}/comments", params={"telegram_user_id": 14}
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_add_comment_to_missing_task_returns_404(client):
    response = await client.post(
        "/tasks/9999/comments", json={"telegram_user_id": 14, "text": "Привет"}
    )
    assert response.status_code == 404


async def test_delete_comment(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 15, "title": "Задача"}
    )
    task_id = create_resp.json()["id"]
    add_resp = await client.post(
        f"/tasks/{task_id}/comments",
        json={"telegram_user_id": 15, "text": "Комментарий"},
    )
    comment_id = add_resp.json()["id"]

    delete_resp = await client.delete(
        f"/tasks/comments/{comment_id}", params={"telegram_user_id": 15}
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get(
        f"/tasks/{task_id}/comments", params={"telegram_user_id": 15}
    )
    assert list_resp.json() == []


async def test_task_list_includes_comment_count(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 16, "title": "Задача"}
    )
    task_id = create_resp.json()["id"]
    await client.post(
        f"/tasks/{task_id}/comments",
        json={"telegram_user_id": 16, "text": "Раз"},
    )
    await client.post(
        f"/tasks/{task_id}/comments",
        json={"telegram_user_id": 16, "text": "Два"},
    )

    tasks = await client.get("/tasks", params={"telegram_user_id": 16})

    assert tasks.json()[0]["comment_count"] == 2


async def test_delete_missing_comment_returns_404(client):
    response = await client.delete(
        "/tasks/comments/9999", params={"telegram_user_id": 15}
    )
    assert response.status_code == 404
