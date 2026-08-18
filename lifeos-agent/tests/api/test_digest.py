"""
REST API дайджестов (см. specs/015-digest-api.md, app/api/digest.py).

Проверка токена здесь отключена через dependency_overrides — она своя и
живёт в tests/api/test_auth.py.

Скрейпер подменён: настоящий ходит в сеть на t.me, а тесты не должны
зависеть ни от интернета, ни от того, что именно сегодня опубликовано в
чужом канале.
"""

from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import require_api_token
from app.db.base import Base
from app.db.session import get_session
from app.digest.repository import DigestRepository
from app.digest.scraper import ChannelPost
from app.digest.service import DigestService
from app.main import app
from tests.support import sqlite_engine

OWNER = 111
STRANGER = 222


def FakePost(post_id: int, text: str) -> ChannelPost:
    """Настоящий ChannelPost, а не своя заглушка: у самодельной не
    оказалось поля url, и тест падал не на том, что проверял."""
    return ChannelPost(
        post_id=post_id,
        text=text,
        url=f"https://t.me/greenpeace/{post_id}",
        published_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )


class FakeScraper:
    """Отдаёт заранее заданные посты. Пустой список = новых постов нет."""

    def __init__(self, posts=None):
        self.posts = posts if posts is not None else [FakePost(10, "привет")]

    async def fetch_new_posts(self, channel_username, last_seen_post_id=None):
        if last_seen_post_id is None:
            return self.posts
        return [p for p in self.posts if p.post_id > last_seen_post_id]


@pytest_asyncio.fixture
async def env(monkeypatch):
    """Приложение с SQLite в памяти и подменённым скрейпером."""
    engine = sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    scraper = FakeScraper()

    def build_service(session):
        return DigestService(DigestRepository(session), scraper)

    monkeypatch.setattr("app.api.digest.build_digest_service", build_service)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_api_token] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, scraper

    app.dependency_overrides.clear()
    await engine.dispose()


async def _create(client, name="ESG", frequency=None):
    payload = {"telegram_user_id": OWNER, "name": name}
    if frequency:
        payload["auto_frequency"] = frequency
    return await client.post("/digest", json=payload)


# --- Темы ------------------------------------------------------------


async def test_create_digest(env):
    client, _ = env
    response = await _create(client, "ESG", "daily")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ESG"
    assert body["auto_frequency"] == "daily"
    assert body["channels"] == []


async def test_duplicate_name_is_rejected(env):
    client, _ = env
    await _create(client, "ESG")
    response = await _create(client, "ESG")
    assert response.status_code == 400


async def test_name_of_two_words_is_rejected(env):
    """Имена — один токен: команды бота разбирают context.args по
    пробелам (см. app/digest/models.py)."""
    client, _ = env
    response = await _create(client, "зелёная энергетика")
    assert response.status_code == 400


async def test_frequency_typo_is_rejected_by_schema(env):
    """Свободная строка доехала бы до БД и молча отключила автоотправку —
    тема просто перестала бы приходить."""
    client, _ = env
    response = await client.post(
        "/digest",
        json={"telegram_user_id": OWNER, "name": "ESG", "auto_frequency": "dayly"},
    )
    assert response.status_code == 422


async def test_list_returns_only_own_digests(env):
    client, _ = env
    await _create(client, "ESG")
    response = await client.get(f"/digest?telegram_user_id={STRANGER}")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_includes_channels(env):
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    await client.post(
        f"/digest/{digest_id}/channels",
        json={"telegram_user_id": OWNER, "channel_username": "@greenpeace"},
    )
    body = (await client.get(f"/digest?telegram_user_id={OWNER}")).json()
    assert [c["channel_username"] for c in body[0]["channels"]] == ["greenpeace"]


# --- Каналы ----------------------------------------------------------


async def test_add_channel(env):
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    response = await client.post(
        f"/digest/{digest_id}/channels",
        json={"telegram_user_id": OWNER, "channel_username": "@greenpeace"},
    )
    assert response.status_code == 201
    # Имя нормализуется: без @ и без t.me/
    assert response.json()["channel_username"] == "greenpeace"


async def test_add_channel_to_foreign_digest_is_404(env):
    """Чужая тема неотличима от несуществующей (owned_or_none)."""
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    response = await client.post(
        f"/digest/{digest_id}/channels",
        json={"telegram_user_id": STRANGER, "channel_username": "@greenpeace"},
    )
    assert response.status_code == 404


async def test_add_duplicate_channel_is_400(env):
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    body = {"telegram_user_id": OWNER, "channel_username": "@greenpeace"}
    await client.post(f"/digest/{digest_id}/channels", json=body)
    response = await client.post(f"/digest/{digest_id}/channels", json=body)
    assert response.status_code == 400


async def test_remove_channel(env):
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    channel = (
        await client.post(
            f"/digest/{digest_id}/channels",
            json={"telegram_user_id": OWNER, "channel_username": "@greenpeace"},
        )
    ).json()

    response = await client.delete(
        f"/digest/channels/{channel['id']}?telegram_user_id={OWNER}"
    )
    assert response.status_code == 204

    body = (await client.get(f"/digest?telegram_user_id={OWNER}")).json()
    assert body[0]["channels"] == []


async def test_remove_foreign_channel_is_404(env):
    client, _ = env
    digest_id = (await _create(client)).json()["id"]
    channel = (
        await client.post(
            f"/digest/{digest_id}/channels",
            json={"telegram_user_id": OWNER, "channel_username": "@greenpeace"},
        )
    ).json()

    response = await client.delete(
        f"/digest/channels/{channel['id']}?telegram_user_id={STRANGER}"
    )
    assert response.status_code == 404


# --- Отправка --------------------------------------------------------


@pytest_asyncio.fixture
async def digest_with_channel(env):
    client, scraper = env
    digest_id = (await _create(client)).json()["id"]
    await client.post(
        f"/digest/{digest_id}/channels",
        json={"telegram_user_id": OWNER, "channel_username": "@greenpeace"},
    )
    return client, scraper, digest_id


async def test_send_delivers_and_returns_text(digest_with_channel, monkeypatch):
    client, scraper, digest_id = digest_with_channel
    # Пост новее водяного знака, выставленного при добавлении канала.
    scraper.posts = [FakePost(10, "старое"), FakePost(11, "свежая новость")]

    sent = []

    async def fake_send(text, settings=None):
        sent.append(text)

    monkeypatch.setattr("app.api.digest.send_to_owner", fake_send)
    monkeypatch.setattr("app.api.digest.get_ai_client", lambda: None)

    response = await client.post(f"/digest/{digest_id}/send?telegram_user_id={OWNER}")
    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is True
    assert "свежая новость" in body["text"]
    assert sent and "свежая новость" in sent[0]


async def test_send_returns_text_even_when_delivery_fails(
    digest_with_channel, monkeypatch
):
    """Ключевой сценарий спеки: сборка текста УЖЕ сдвинула водяной знак и
    закоммитила его. Промолчать об ошибке значит потерять посты навсегда,
    поэтому текст обязан вернуться в ответе."""
    client, scraper, digest_id = digest_with_channel
    scraper.posts = [FakePost(10, "старое"), FakePost(11, "свежая новость")]

    from app.telegram.notifier import NotifyError

    async def failing_send(text, settings=None):
        raise NotifyError("Telegram недоступен")

    monkeypatch.setattr("app.api.digest.send_to_owner", failing_send)
    monkeypatch.setattr("app.api.digest.get_ai_client", lambda: None)

    response = await client.post(f"/digest/{digest_id}/send?telegram_user_id={OWNER}")
    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is False
    assert "свежая новость" in body["text"]
    assert body["error"] == "Telegram недоступен"


async def test_send_without_new_posts_is_not_an_error(digest_with_channel, monkeypatch):
    """Новых постов нет — ровно так же тихо пропускает фоновая джоба."""
    client, scraper, digest_id = digest_with_channel
    # Водяной знак уже стоит на 10, ничего свежее не появилось.
    scraper.posts = [FakePost(10, "старое")]

    monkeypatch.setattr("app.api.digest.get_ai_client", lambda: None)

    response = await client.post(f"/digest/{digest_id}/send?telegram_user_id={OWNER}")
    assert response.status_code == 200
    assert response.json() == {"delivered": False, "text": None, "error": None}


async def test_send_foreign_digest_is_404(digest_with_channel, monkeypatch):
    client, _, digest_id = digest_with_channel
    monkeypatch.setattr("app.api.digest.get_ai_client", lambda: None)

    response = await client.post(
        f"/digest/{digest_id}/send?telegram_user_id={STRANGER}"
    )
    assert response.status_code == 404
