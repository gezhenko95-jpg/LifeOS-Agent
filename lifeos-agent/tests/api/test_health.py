"""
/health отдаёт хеш развёрнутого коммита — им сверяют прод с гитом, не
заходя на сервер (см. scripts/deploy.sh, AUDIT.md про три копии кода).
"""

from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import health
from app.db.base import Base
from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_with_db():
    """/health/ready реально ходит в БД (см. AUDIT.md, раздел 5) —
    нужна настоящая (пусть и in-memory) сессия, а не просто ASGI-клиент
    без override, как у /health."""
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


class _BrokenSession:
    async def execute(self, *args, **kwargs):
        raise SQLAlchemyError("подключение к БД недоступно")


@pytest_asyncio.fixture
async def client_with_broken_db():
    async def override_get_session():
        yield _BrokenSession()

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def test_health_reports_deployed_commit(client, tmp_path, monkeypatch):
    commit_file = tmp_path / "DEPLOYED_COMMIT"
    commit_file.write_text("ee7b9a9abc\n")
    monkeypatch.setattr(health, "_DEPLOYED_COMMIT_FILE", commit_file)

    body = (await client.get("/health")).json()

    assert body["commit"] == "ee7b9a9abc"


async def test_health_survives_missing_commit_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(health, "_DEPLOYED_COMMIT_FILE", tmp_path / "нет-такого")

    body = (await client.get("/health")).json()

    assert body["status"] == "healthy"
    assert body["commit"] == "unknown"


async def test_health_survives_directory_instead_of_file(client, tmp_path, monkeypatch):
    """Docker создаёт пустую ДИРЕКТОРИЮ на месте незамонтированного файла
    в bind mount — те же грабли, что у token.json."""
    as_dir = tmp_path / "DEPLOYED_COMMIT"
    as_dir.mkdir()
    monkeypatch.setattr(health, "_DEPLOYED_COMMIT_FILE", Path(as_dir))

    body = (await client.get("/health")).json()

    assert body["commit"] == "unknown"


async def test_ready_returns_200_when_db_reachable(client_with_db):
    response = await client_with_db.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_ready_returns_503_when_db_unreachable(client_with_broken_db):
    response = await client_with_broken_db.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not ready"


async def test_live_always_returns_200(client):
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"
