"""
MediaInboxService.handle_photo — композиция DriveClient/WatchlistService/
classify_image (замокана целиком, отдельно протестирована в
test_classify.py). См. specs/010-media-inbox.md (Фаза 2).
"""

from unittest.mock import AsyncMock, MagicMock

from app.drive.client import DriveServiceError
from app.media_inbox.classify import ImageClassification
from app.media_inbox.service import MediaInboxService


def _drive_client() -> MagicMock:
    drive = MagicMock()
    drive.ensure_folder.return_value = "folder-id"
    drive.upload_file.return_value = "https://drive.google.com/file1"
    return drive


def _watchlist_service() -> AsyncMock:
    service = AsyncMock()
    service.create_item.return_value = MagicMock(title="Дюна")
    return service


async def test_sketch_uploads_without_watchlist(monkeypatch):
    monkeypatch.setattr(
        "app.media_inbox.service.classify_image",
        AsyncMock(return_value=ImageClassification(category="sketch", title=None)),
    )
    drive = _drive_client()
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, AsyncMock())

    reply = await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    drive.ensure_folder.assert_called_once_with("Эскизы")
    watchlist.create_item.assert_not_called()
    assert "Эскизы" in reply


async def test_movie_with_title_creates_watchlist_item(monkeypatch):
    monkeypatch.setattr(
        "app.media_inbox.service.classify_image",
        AsyncMock(return_value=ImageClassification(category="movie", title="Дюна")),
    )
    drive = _drive_client()
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, AsyncMock())

    reply = await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    drive.ensure_folder.assert_called_once_with("Кино и книги")
    watchlist.create_item.assert_awaited_once_with(
        1,
        "Дюна",
        media_type="movie",
        source="photo",
        drive_file_url="https://drive.google.com/file1",
    )
    assert "Кино и книги" in reply
    assert "Дюна" in reply


async def test_movie_without_title_skips_watchlist(monkeypatch):
    monkeypatch.setattr(
        "app.media_inbox.service.classify_image",
        AsyncMock(return_value=ImageClassification(category="movie", title=None)),
    )
    drive = _drive_client()
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, AsyncMock())

    await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    watchlist.create_item.assert_not_called()


async def test_classification_failure_falls_back_to_other(monkeypatch):
    monkeypatch.setattr(
        "app.media_inbox.service.classify_image", AsyncMock(return_value=None)
    )
    drive = _drive_client()
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, AsyncMock())

    reply = await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    drive.ensure_folder.assert_called_once_with("Разное")
    watchlist.create_item.assert_not_called()
    assert "Разное" in reply


async def test_without_ai_client_skips_classification_entirely(monkeypatch):
    classify_mock = AsyncMock()
    monkeypatch.setattr("app.media_inbox.service.classify_image", classify_mock)
    drive = _drive_client()
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, ai_client=None)

    reply = await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    classify_mock.assert_not_awaited()
    drive.ensure_folder.assert_called_once_with("Разное")
    assert "Разное" in reply


async def test_drive_error_returns_graceful_message(monkeypatch):
    monkeypatch.setattr(
        "app.media_inbox.service.classify_image",
        AsyncMock(return_value=ImageClassification(category="sketch", title=None)),
    )
    drive = _drive_client()
    drive.ensure_folder.side_effect = DriveServiceError("boom")
    watchlist = _watchlist_service()
    service = MediaInboxService(drive, watchlist, AsyncMock())

    reply = await service.handle_photo(1, "photo.jpg", b"data", "image/jpeg")

    assert "не получилось" in reply.lower()
    watchlist.create_item.assert_not_called()
