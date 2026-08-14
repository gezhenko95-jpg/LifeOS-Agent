"""
DriveClient — google-api-python-client замокан целиком (googleapiclient.
discovery.build, Credentials.from_authorized_user_file), реальных
сетевых вызовов к Google нет. См. specs/010-media-inbox.md (Фаза 2).
"""

from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from app.core.config import Settings
from app.drive.client import DriveClient, DriveServiceError, get_drive_client


def _http_error(status: str = "500") -> HttpError:
    return HttpError(httplib2.Response({"status": status}), b"boom")


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_creates_when_missing(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "new123"
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    folder_id = client.ensure_folder("Эскизы")

    assert folder_id == "new123"
    service.files.return_value.create.assert_called_once()


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_reuses_existing(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "existing1"}]
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    folder_id = client.ensure_folder("Эскизы")

    assert folder_id == "existing1"
    service.files.return_value.create.assert_not_called()


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_caches_across_calls(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "existing1"}]
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    client.ensure_folder("Эскизы")
    client.ensure_folder("Эскизы")

    assert service.files.return_value.list.call_count == 1


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_with_parent_creates_nested(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "child123"
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    folder_id = client.ensure_folder("Эскизы", parent_id="root-folder")

    assert folder_id == "child123"
    _, kwargs = service.files.return_value.create.call_args
    assert kwargs["body"]["parents"] == ["root-folder"]


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_cache_distinguishes_by_parent(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "existing1"}]
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    client.ensure_folder("Разное")  # без родителя
    client.ensure_folder("Разное", parent_id="root-folder")  # с родителем — не кэш

    assert service.files.return_value.list.call_count == 2


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_ensure_folder_wraps_http_error(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.list.return_value.execute.side_effect = _http_error()
    mock_build.return_value = service

    client = DriveClient("token.json")
    with pytest.raises(DriveServiceError):
        client.ensure_folder("Эскизы")


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_upload_file_returns_web_view_link(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "file1",
        "webViewLink": "https://drive.google.com/file1",
    }
    mock_build.return_value = service

    client = DriveClient("token.json")
    url = client.upload_file("folder1", "test.jpg", b"binary-data", "image/jpeg")

    assert url == "https://drive.google.com/file1"


@patch("app.drive.client.build")
@patch("app.drive.client.Credentials.from_authorized_user_file")
def test_upload_file_wraps_http_error(mock_creds, mock_build):
    service = MagicMock()
    service.files.return_value.create.return_value.execute.side_effect = _http_error()
    mock_build.return_value = service

    client = DriveClient("token.json")
    with pytest.raises(DriveServiceError):
        client.upload_file("folder1", "test.jpg", b"data", "image/jpeg")


def test_get_drive_client_returns_none_when_token_missing(tmp_path):
    settings = Settings(
        telegram_bot_token="x", drive_token_file=str(tmp_path / "missing.json")
    )

    assert get_drive_client(settings) is None
