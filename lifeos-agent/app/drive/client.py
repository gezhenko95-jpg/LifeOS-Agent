"""
Тонкая обёртка над Google Drive API (Фаза 2 Media Inbox, см.
specs/010-media-inbox.md). OAuth от имени пользователя (не сервис-
аккаунт — личный Диск, не Workspace), токен получен один раз локально
через scripts/drive_auth.py и смонтирован в контейнер только для чтения
(docker-compose.yml) — сам DriveClient token.json не переписывает,
обновление access-токена по refresh_token происходит в памяти на
каждый вызов API, если понадобится (стандартное поведение
google-auth).
"""

import io
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveServiceError(Exception):
    """Любая ошибка вызова Drive API."""


class DriveClient:
    def __init__(self, token_file: str) -> None:
        creds = Credentials.from_authorized_user_file(token_file)
        self._service = build("drive", "v3", credentials=creds)
        self._folder_cache: dict[str, str] = {}

    def ensure_folder(self, name: str) -> str:
        """Id папки `name` в корне Диска — создаёт при отсутствии.
        Кэшируется на время жизни клиента, чтобы не искать папку заново
        на каждую загрузку файла."""
        if name in self._folder_cache:
            return self._folder_cache[name]

        try:
            query = (
                f"name = '{name}' and mimeType = '{_FOLDER_MIME_TYPE}' "
                "and trashed = false"
            )
            result = self._service.files().list(q=query, fields="files(id)").execute()
            files = result.get("files", [])
            if files:
                folder_id = files[0]["id"]
            else:
                metadata = {"name": name, "mimeType": _FOLDER_MIME_TYPE}
                created = (
                    self._service.files().create(body=metadata, fields="id").execute()
                )
                folder_id = created["id"]
        except HttpError as exc:
            raise DriveServiceError(
                f"Не удалось получить/создать папку: {exc}"
            ) from exc

        self._folder_cache[name] = folder_id
        return folder_id

    def upload_file(
        self, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> str:
        """Загрузить файл в папку, вернуть ссылку для просмотра (пустая
        строка, если Drive её не вернул — не должно случаться в норме)."""
        try:
            metadata = {"name": filename, "parents": [folder_id]}
            media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
            created = (
                self._service.files()
                .create(body=metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
        except HttpError as exc:
            raise DriveServiceError(f"Не удалось загрузить файл: {exc}") from exc
        return created.get("webViewLink", "")


def get_drive_client(settings: Settings | None = None) -> DriveClient | None:
    """None, если token.json не найден/не настроен — Фаза 2 полностью
    опциональна, как и AI-клиент (см. app/ai/client.py::get_ai_client),
    остальной бот работает без неё."""
    settings = settings or get_settings()
    try:
        return DriveClient(settings.drive_token_file)
    except (OSError, ValueError) as exc:
        # OSError — не только "файла нет" (FileNotFoundError), но и
        # IsADirectoryError: Docker создаёт пустую директорию на месте
        # незамонтированного файла в bind mount (см. docker-compose.yml).
        logger.info("Google Drive не настроен (%s) — Media Inbox выключен", exc)
        return None
