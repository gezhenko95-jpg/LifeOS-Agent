"""
Media Inbox Service — приём фото из Telegram: классификация → раскладка
по Google Drive → (для фильма/книги) связка с Watchlist. См.
specs/010-media-inbox.md (Фаза 2).

Композиция уже существующих слоёв (DriveClient/WatchlistService/AI), как
InsightsService — своей таблицы нет.
"""

import asyncio
import logging

from app.ai.client import AIClient
from app.drive.client import DriveClient, DriveServiceError
from app.media_inbox.classify import classify_image
from app.watchlist.service import WatchlistService

logger = logging.getLogger(__name__)

# Всё, что шлёт пользователь, лежит внутри одной корневой папки LifeOS —
# не мусорим в корне Диска, легко найти/убрать целиком.
_ROOT_FOLDER = "LifeOS"

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
    ) -> tuple[bool, str]:
        """(успех, текст). Успех=False только при сбое самого Drive —
        вызывающий код (см. app/telegram/handlers.py) по этому флагу
        решает, можно ли удалить оригинал фото из чата: файл ещё нигде
        не сохранён, значит и удалять из Telegram нельзя, иначе фото
        будет потеряно безвозвратно.

        Классификация не удалась/AI недоступна — молчаливый откат на
        "other" (файл всё равно сохраняется, просто без Watchlist-записи),
        тот же принцип, что и у AI-фолбэков везде в проекте."""
        classification = None
        if self._ai is not None:
            classification = await classify_image(content, mime_type, self._ai)
        category = classification.category if classification else "other"
        title = classification.title if classification else None

        folder_name = _FOLDER_BY_CATEGORY[category]
        try:
            file_url = await asyncio.to_thread(
                self._upload_to_drive, folder_name, filename, content, mime_type
            )
        except DriveServiceError as exc:
            logger.warning("Не удалось сохранить файл на Drive: %s", exc)
            return (
                False,
                "Не получилось сохранить файл на Диск — попробуй ещё раз позже.",
            )

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

        return True, f"Сохранил в «{_ROOT_FOLDER}/{folder_name}» на Диске.{note}"

    def _upload_to_drive(
        self, folder_name: str, filename: str, content: bytes, mime_type: str
    ) -> str:
        """Синхронная часть: google-api-python-client построен на httplib2
        и блокирующий. Вызывается ТОЛЬКО через asyncio.to_thread — иначе
        на время загрузки фото (несколько секунд) встаёт весь event loop:
        бот не отвечает никому и джобы не выполняются (см. AUDIT.md, B-9).

        Три вызова живут в одной функции, чтобы уйти в поток один раз, а
        не три раза подряд.
        """
        root_id = self._drive.ensure_folder(_ROOT_FOLDER)
        folder_id = self._drive.ensure_folder(folder_name, parent_id=root_id)
        return self._drive.upload_file(folder_id, filename, content, mime_type)
