"""
DigestService на моках репозитория и скрейпера (по образцу
tests/watchlist/test_service.py).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.ai.client import AIServiceError
from app.digest.models import Digest, DigestChannel
from app.digest.scraper import ChannelPost, ChannelScrapeError
from app.digest.service import DigestService, normalize_channel_username


def _post(post_id: int, text: str = "Текст поста") -> ChannelPost:
    return ChannelPost(
        post_id=post_id,
        text=text,
        url=f"https://t.me/testchannel/{post_id}",
        published_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda digest: digest
    repo.get_by_name.return_value = None
    repo.get_channel.return_value = None
    repo.list_channels.return_value = []
    return repo


@pytest.fixture
def scraper():
    return AsyncMock()


@pytest.fixture
def service(repository, scraper) -> DigestService:
    return DigestService(repository, scraper)


async def test_create_digest(service, repository):
    digest = await service.create_digest(1, "ESG", "daily")

    assert digest.name == "ESG"
    assert digest.auto_frequency == "daily"
    repository.add.assert_awaited_once()


async def test_create_digest_without_frequency(service):
    digest = await service.create_digest(1, "ESG")

    assert digest.auto_frequency is None


@pytest.mark.parametrize("name", ["   ", "две слова", "x" * 51])
async def test_create_digest_rejects_bad_name(service, name):
    with pytest.raises(ValueError):
        await service.create_digest(1, name)


async def test_create_digest_rejects_unknown_frequency(service):
    with pytest.raises(ValueError):
        await service.create_digest(1, "ESG", "hourly")


async def test_create_digest_rejects_duplicate(service, repository):
    repository.get_by_name.return_value = Digest(telegram_user_id=1, name="ESG")

    with pytest.raises(ValueError):
        await service.create_digest(1, "ESG")


@pytest.mark.parametrize(
    "raw",
    [
        "telegram",
        "@telegram",
        "t.me/telegram",
        "https://t.me/telegram/",
        "t.me/s/telegram",
    ],
)
def test_normalize_channel_username(raw):
    assert normalize_channel_username(raw) == "telegram"


async def test_add_channel_sets_watermark_to_latest_post(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.add_channel.return_value = DigestChannel(
        id=1, digest_id=7, channel_username="telegram"
    )
    scraper.fetch_new_posts.return_value = [_post(100), _post(101)]

    await service.add_channel(1, "ESG", "@telegram")

    repository.add_channel.assert_awaited_once_with(7, "telegram")
    # Иначе первый же дайджест вывалил бы всю видимую историю канала.
    args = repository.update_last_seen_post_id.await_args.args
    assert args[1] == 101


async def test_add_channel_propagates_scrape_error(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    scraper.fetch_new_posts.side_effect = ChannelScrapeError("нет такого канала")

    with pytest.raises(ChannelScrapeError):
        await service.add_channel(1, "ESG", "nosuchchannel")

    repository.add_channel.assert_not_called()


async def test_add_channel_rejects_unknown_digest(service, repository):
    repository.get_by_name.return_value = None

    with pytest.raises(ValueError):
        await service.add_channel(1, "ESG", "telegram")


async def test_add_channel_rejects_foreign_digest(service, repository):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=2, name="ESG")

    with pytest.raises(ValueError):
        await service.add_channel(1, "ESG", "telegram")


async def test_add_channel_rejects_duplicate(service, repository):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.get_channel.return_value = DigestChannel(
        id=1, digest_id=7, channel_username="telegram"
    )

    with pytest.raises(ValueError):
        await service.add_channel(1, "ESG", "telegram")


async def test_remove_channel(service, repository):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    channel = DigestChannel(id=1, digest_id=7, channel_username="telegram")
    repository.get_channel.return_value = channel

    assert await service.remove_channel(1, "ESG", "@telegram") is True
    repository.remove_channel.assert_awaited_once_with(channel)


async def test_remove_channel_returns_false_when_absent(service, repository):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.get_channel.return_value = None

    assert await service.remove_channel(1, "ESG", "telegram") is False


async def test_build_digest_text_returns_none_without_new_posts(
    service, repository, scraper
):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.list_channels.return_value = [
        DigestChannel(
            id=1, digest_id=7, channel_username="telegram", last_seen_post_id=5
        )
    ]
    scraper.fetch_new_posts.return_value = []

    assert await service.build_digest_text(1, "ESG") is None


async def test_build_digest_text_without_ai_lists_posts(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.list_channels.return_value = [
        DigestChannel(
            id=1, digest_id=7, channel_username="telegram", last_seen_post_id=5
        )
    ]
    scraper.fetch_new_posts.return_value = [_post(6, "Новость про лес")]

    text = await service.build_digest_text(1, "ESG")

    assert "ESG" in text
    assert "Новость про лес" in text
    assert "https://t.me/testchannel/6" in text


async def test_build_digest_text_with_ai_returns_summary(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.list_channels.return_value = [
        DigestChannel(
            id=1, digest_id=7, channel_username="telegram", last_seen_post_id=5
        )
    ]
    scraper.fetch_new_posts.return_value = [_post(6, "Новость про лес")]
    ai_client = AsyncMock()
    ai_client.complete.return_value = "• Про лес"

    text = await service.build_digest_text(1, "ESG", ai_client=ai_client)

    assert "• Про лес" in text
    assert "https://t.me/testchannel/6" not in text


async def test_build_digest_text_falls_back_when_ai_fails(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    repository.list_channels.return_value = [
        DigestChannel(
            id=1, digest_id=7, channel_username="telegram", last_seen_post_id=5
        )
    ]
    scraper.fetch_new_posts.return_value = [_post(6, "Новость про лес")]
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")

    text = await service.build_digest_text(1, "ESG", ai_client=ai_client)

    assert "Новость про лес" in text


async def test_build_digest_text_advances_watermark(service, repository, scraper):
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    channel = DigestChannel(
        id=1, digest_id=7, channel_username="telegram", last_seen_post_id=5
    )
    repository.list_channels.return_value = [channel]
    scraper.fetch_new_posts.return_value = [_post(6), _post(7)]

    await service.build_digest_text(1, "ESG")

    repository.update_last_seen_post_id.assert_awaited_once_with(channel, 7)


async def test_build_digest_text_survives_broken_channel(service, repository, scraper):
    """Один недоступный канал не должен уносить с собой весь дайджест —
    и его watermark не двигается, посты придут в следующий прогон."""
    repository.get_by_name.return_value = Digest(id=7, telegram_user_id=1, name="ESG")
    broken = DigestChannel(id=1, digest_id=7, channel_username="broken")
    alive = DigestChannel(
        id=2, digest_id=7, channel_username="telegram", last_seen_post_id=5
    )
    repository.list_channels.return_value = [broken, alive]

    async def fetch(channel_username, after_post_id=None):
        if channel_username == "broken":
            raise ChannelScrapeError("канал пропал")
        return [_post(6, "Живой пост")]

    scraper.fetch_new_posts.side_effect = fetch

    text = await service.build_digest_text(1, "ESG")

    assert "Живой пост" in text
    repository.update_last_seen_post_id.assert_awaited_once_with(alive, 6)
