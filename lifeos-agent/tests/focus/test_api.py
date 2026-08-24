"""Интеграционный тест REST API фокус-сессий (specs/026)."""

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


async def test_start_session_defaults(client):
    response = await client.post("/focus/sessions", json={"telegram_user_id": 1})
    assert response.status_code == 201
    body = response.json()
    assert body["work_minutes"] == 25
    assert body["break_minutes"] == 5
    assert body["status"] == "in_progress"


async def test_start_session_custom_duration(client):
    response = await client.post(
        "/focus/sessions",
        json={"telegram_user_id": 1, "work_minutes": 40, "break_minutes": 10},
    )
    assert response.json()["work_minutes"] == 40


async def test_start_session_conflict_returns_400(client):
    await client.post("/focus/sessions", json={"telegram_user_id": 2})

    response = await client.post("/focus/sessions", json={"telegram_user_id": 2})

    assert response.status_code == 400


async def test_get_active_session(client):
    await client.post("/focus/sessions", json={"telegram_user_id": 3})

    response = await client.get(
        "/focus/sessions/active", params={"telegram_user_id": 3}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_get_active_session_none(client):
    response = await client.get(
        "/focus/sessions/active", params={"telegram_user_id": 999}
    )

    assert response.status_code == 200
    assert response.json() is None


async def test_cancel_session(client):
    create_resp = await client.post("/focus/sessions", json={"telegram_user_id": 4})
    session_id = create_resp.json()["id"]

    response = await client.post(
        f"/focus/sessions/{session_id}/cancel", params={"telegram_user_id": 4}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    active_resp = await client.get(
        "/focus/sessions/active", params={"telegram_user_id": 4}
    )
    assert active_resp.json() is None


async def test_cancel_missing_session_returns_404(client):
    response = await client.post(
        "/focus/sessions/9999/cancel", params={"telegram_user_id": 4}
    )
    assert response.status_code == 404


async def test_stats_zero_when_no_sessions(client):
    response = await client.get("/focus/stats", params={"telegram_user_id": 5})

    assert response.status_code == 200
    assert response.json() == {"completed_count": 0, "total_minutes": 0}
