from unittest.mock import AsyncMock

import pytest

from app.ai.client import AIServiceError
from app.watchlist.models import WatchlistItem
from app.watchlist.service import WatchlistService


@pytest.fixture
def repository():
    repo = AsyncMock()
    repo.add.side_effect = lambda item: item
    repo.save.side_effect = lambda item: item
    return repo


async def test_create_item(repository):
    service = WatchlistService(repository)

    item = await service.create_item(1, "Дюна", media_type="movie")

    assert item.title == "Дюна"
    assert item.media_type == "movie"
    assert item.status == "to_watch"
    assert item.source == "manual"
    assert item.drive_file_url is None
    repository.add.assert_awaited_once()


async def test_create_item_from_photo_source(repository):
    service = WatchlistService(repository)

    item = await service.create_item(
        1,
        "Дюна",
        media_type="movie",
        source="photo",
        drive_file_url="https://drive.google.com/file1",
    )

    assert item.source == "photo"
    assert item.drive_file_url == "https://drive.google.com/file1"


async def test_create_item_defaults_to_other(repository):
    service = WatchlistService(repository)

    item = await service.create_item(1, "Дюна")

    assert item.media_type == "other"


async def test_create_item_empty_title_raises(repository):
    service = WatchlistService(repository)

    with pytest.raises(ValueError):
        await service.create_item(1, "   ")


async def test_create_item_invalid_media_type_raises(repository):
    service = WatchlistService(repository)

    with pytest.raises(ValueError):
        await service.create_item(1, "Дюна", media_type="podcast")


async def test_list_active_items(repository):
    repository.list_by_user.return_value = [
        WatchlistItem(telegram_user_id=1, title="X")
    ]
    service = WatchlistService(repository)

    items = await service.list_active_items(1)

    assert len(items) == 1
    repository.list_by_user.assert_awaited_once_with(1, status="to_watch")


async def test_list_all_items_passes_no_status_filter(repository):
    repository.list_by_user.return_value = [
        WatchlistItem(telegram_user_id=1, title="X", status="to_watch"),
        WatchlistItem(telegram_user_id=1, title="Y", status="done"),
    ]
    service = WatchlistService(repository)

    items = await service.list_all_items(1)

    assert len(items) == 2
    repository.list_by_user.assert_awaited_once_with(1, status=None)


async def test_mark_done_found(repository):
    item = WatchlistItem(id=1, telegram_user_id=1, title="Дюна", status="to_watch")
    repository.get_by_id.return_value = item
    service = WatchlistService(repository)

    result = await service.mark_done(1)

    assert result.status == "done"
    assert result.completed_at is not None


async def test_mark_done_not_found(repository):
    repository.get_by_id.return_value = None
    service = WatchlistService(repository)

    result = await service.mark_done(999)

    assert result is None


async def test_delete_item_found(repository):
    item = WatchlistItem(id=1, telegram_user_id=1, title="Дюна")
    repository.get_by_id.return_value = item
    service = WatchlistService(repository)

    result = await service.delete_item(1)

    assert result is item
    repository.delete.assert_awaited_once_with(item)


async def test_delete_item_not_found(repository):
    repository.get_by_id.return_value = None
    service = WatchlistService(repository)

    result = await service.delete_item(999)

    assert result is None


async def test_pick_recommendation_empty_list_returns_none(repository):
    repository.list_by_user.return_value = []
    service = WatchlistService(repository)

    result = await service.pick_recommendation(1)

    assert result is None


async def test_pick_recommendation_without_ai(repository):
    repository.list_by_user.return_value = [
        WatchlistItem(id=1, telegram_user_id=1, title="Дюна")
    ]
    service = WatchlistService(repository)

    result = await service.pick_recommendation(1)

    assert result == "Как насчёт «Дюна»?"


async def test_pick_recommendation_with_ai_appends_comment(repository):
    repository.list_by_user.return_value = [
        WatchlistItem(id=1, telegram_user_id=1, title="Дюна")
    ]
    ai_client = AsyncMock()
    ai_client.complete.return_value = "  Отличный выбор для вечера.  "
    service = WatchlistService(repository)

    result = await service.pick_recommendation(1, ai_client=ai_client)

    assert result == "Как насчёт «Дюна»? Отличный выбор для вечера."


async def test_pick_recommendation_ai_error_falls_back(repository):
    repository.list_by_user.return_value = [
        WatchlistItem(id=1, telegram_user_id=1, title="Дюна")
    ]
    ai_client = AsyncMock()
    ai_client.complete.side_effect = AIServiceError("boom")
    service = WatchlistService(repository)

    result = await service.pick_recommendation(1, ai_client=ai_client)

    assert result == "Как насчёт «Дюна»?"
