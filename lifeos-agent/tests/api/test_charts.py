"""
Интеграционный тест REST API графика (specs/007, довесок — карточка
"Итоги недели" на /ui). Сама отрисовка уже проверена
tests/scheduler/test_charts.py — здесь только сам эндпоинт: 200+PNG,
когда есть что показать, 404, когда нечего.
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


async def test_weekly_chart_404_when_nothing_to_show(client):
    response = await client.get("/charts/weekly", params={"telegram_user_id": 1})
    assert response.status_code == 404


async def test_weekly_chart_returns_png_when_task_completed(client):
    create_resp = await client.post(
        "/tasks", json={"telegram_user_id": 2, "title": "Отчёт"}
    )
    task_id = create_resp.json()["id"]
    await client.patch(
        f"/tasks/{task_id}",
        params={"telegram_user_id": 2},
        json={"status": "completed"},
    )

    response = await client.get("/charts/weekly", params={"telegram_user_id": 2})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


async def test_weekly_chart_requires_auth_token(client):
    """Без переопределения require_api_token эндпоинт не отдаёт график
    молча — тот же принцип, что у остальных API (пустой/отсутствующий
    токен закрывает доступ, см. tests/api/test_auth.py)."""
    app.dependency_overrides.pop(require_api_token, None)
    response = await client.get("/charts/weekly", params={"telegram_user_id": 1})
    assert response.status_code != 200
