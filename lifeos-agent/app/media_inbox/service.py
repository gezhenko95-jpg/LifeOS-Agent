"""
Media Inbox Service — приём фото из Telegram: классификация → раскладка
по Google Drive → (для фильма/книги) связка с Watchlist. См.
specs/010-media-inbox.md (Фаза 2).

Композиция уже существующих слоёв (DriveClient/WatchlistService/AI), как
InsightsService — своей таблицы нет.
"""

import logging

from app.ai.client import AIClient
from app.drive.client import DriveClient, DriveServiceError
from app.media_inbox.classify import classify_image
from app.watchlist.service import WatchlistService

logger = logging.getLogger(__name__)

_FOLDER_BY_CATEGORY = {
    "sketch": "Эскизы",
    "movie": "Кино и книги",
    "book": "Кино и книги",
    "other": "Разное",
}
_WATCHLIST_CATEGORIES = {"movie", "book"}


class MediaInboxService:
    def __init__(
        self,
        drive_client: DriveClient,
        watchlist_service: WatchlistService,
        ai_client: AIClient | None,
    ) -> None:
        self._drive = drive_client
        self._watchlist = watchlist_service
        self._ai = ai_client

    async def handle_photo(
        self, telegram_user_id: int, filename: str, content: bytes, mime_type: str
    ) -> str:
        """Классификация не удалась/AI недоступна — молчаливый откат на
        "other" (файл всё равно сохраняется, просто без Watchlist-записи),
        тот же принцип, что и у AI-фолбэков везде в проекте."""
        classification = None
        if self._ai is not None:
            classification = await classify_image(content, mime_type, self._ai)
        category = classification.category if classification else "other"
        title = classification.title if classification else None

        folder_name = _FOLDER_BY_CATEGORY[category]
        try:
            folder_id = self._drive.ensure_folder(folder_name)
            file_url = self._drive.upload_file(folder_id, filename, content, mime_type)
        except DriveServiceError as exc:
            logger.warning("Не удалось сохранить файл на Drive: %s", exc)
            return "Не получилось сохранить файл на Диск — попробуй ещё раз позже."

        note = ""
        if category in _WATCHLIST_CATEGORIES and title:
            item = await self._watchlist.create_item(
                telegram_user_id,
                title,
                media_type=category,
                source="photo",
                drive_file_url=file_url,
            )
            note = f"\nДобавил в список: «{item.title}»."

        return f"Сохранил в «{folder_name}» на Диске.{note}"
