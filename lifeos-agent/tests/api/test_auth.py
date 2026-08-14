"""
Аутентификация REST API (см. app/api/deps.py, AUDIT.md C-2).

Остальные тесты API отключают проверку токена через
dependency_overrides — здесь она проверяется на настоящем приложении,
включая случай "токен в настройках не задан".
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app

_TOKEN = "test-token-123"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def with_token(monkeypatch):
    """Подменить настройки так, чтобы api_token был задан.

    get_settings обёрнут в lru_cache, поэтому подменяем саму функцию в
    модуле, где её вызывает зависимость.
    """
    settings = Settings(api_token=_TOKEN)
    monkeypatch.setattr("app.api.deps.get_settings", lambda: settings)
    return settings


@pytest.fixture
def without_token(monkeypatch):
    settings = Settings(api_token="")
    monkeypatch.setattr("app.api.deps.get_settings", lambda: settings)
    return settings


async def test_request_without_token_is_rejected(client, with_token):
    response = await client.get("/tasks?telegram_user_id=1")
    assert response.status_code == 401


async def test_request_with_wrong_token_is_rejected(client, with_token):
    response = await client.get(
        "/tasks?telegram_user_id=1", headers={"X-API-Token": "wrong-token"}
    )
    assert response.status_code == 401


async def test_unconfigured_token_closes_api_instead_of_opening_it(
    client, without_token
):
    """Пустой api_token = API закрыт (503), а НЕ открыт всем подряд.

    Забытая настройка должна ломать доступ, а не молча снимать защиту —
    именно так дневник и оказался публично читаемым (AUDIT.md, C-2).
    """
    response = await client.get(
        "/tasks?telegram_user_id=1", headers={"X-API-Token": "any-token"}
    )
    assert response.status_code == 503


async def test_health_stays_open_without_token(client, with_token):
    """/health нужен снаружи для проверки живости и приватных данных не
    отдаёт — он намеренно вне защиты."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_correct_token_passes_auth(client, with_token):
    """Правильный токен проходит замок и запрос доходит до эндпоинта."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        response = await client.get(
            "/tasks?telegram_user_id=1", headers={"X-API-Token": _TOKEN}
        )
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
