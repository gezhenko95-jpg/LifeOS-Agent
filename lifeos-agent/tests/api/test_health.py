"""
/health отдаёт хеш развёрнутого коммита — им сверяют прод с гитом, не
заходя на сервер (см. scripts/deploy.sh, AUDIT.md про три копии кода).
"""

from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import health
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
