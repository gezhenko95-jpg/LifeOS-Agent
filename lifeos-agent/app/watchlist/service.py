"""
Watchlist Service.

Вся бизнес-логика записей "посмотреть/прочитать позже" находится здесь.
Repository — только БД, Conversation/Telegram — только вызывают этот
сервис. См. specs/010-media-inbox.md (Фаза 1).
"""

import logging
import random
from datetime import datetime, timezone
from typing import Optional

from app.ai.client import AIClient, AIServiceError
from app.core.ownership import owned_or_none
from app.watchlist.books import GoogleBooksClient
from app.watchlist.models import WatchlistItem
from app.watchlist.repository import WatchlistRepository
from app.watchlist.tmdb import TMDbClient

logger = logging.getLogger(__name__)

TO_WATCH = "to_watch"
DONE = "done"
_VALID_MEDIA_TYPES = {"movie", "book", "other"}

_RECOMMENDATION_SYSTEM_PROMPT = (
    "Ты — личный ассистент пользователя. Ниже список фильмов/книг, "
    "которые пользователь хочет посмотреть/прочитать, и один вариант, "
    "выбранный случайно. Напиши ОДНО короткое (не более 20 слов) "
    "объяснение на русском, почему стоит выбрать именно его сегодня — "
    "без предисловий, без кавычек и markdown. Не выбирай другой вариант, "
    "только прокомментируй уже выбранный. Верни только текст."
)


class WatchlistService:
    def __init__(self, repository: WatchlistRepository) -> None:
        self._repository = repository

    async def create_item(
        self,
        telegram_user_id: int,
        title: str,
        media_type: str = "other",
        source: str = "manual",
        drive_file_url: Optional[str] = None,
        tmdb_client: TMDbClient | None = None,
        books_client: GoogleBooksClient | None = None,
    ) -> WatchlistItem:
        """`tmdb_client` — обогащение карточки обложкой и описанием (см.
        app/watchlist/tmdb.py). Необязательное и полностью тихое: нет
        клиента, нет сети, ничего не нашлось — запись сохраняется
        текстом, ровно как раньше."""
        title = title.strip()
        if not title:
            raise ValueError("Название не может быть пустым")
        if media_type not in _VALID_MEDIA_TYPES:
            raise ValueError(f"Неизвестный тип: {media_type}")

        item = WatchlistItem(
            telegram_user_id=telegram_user_id,
            title=title,
            media_type=media_type,
            status=TO_WATCH,
            source=source,
            drive_file_url=drive_file_url,
        )

        # У каждого типа свой источник карточки: TMDb знает кино, но не
        # книги, Google Books — наоборот.
        if media_type == "book":
            if books_client is not None:
                await self._enrich_from_books(item, books_client)
        elif tmdb_client is not None:
            await self._enrich_from_tmdb(item, tmdb_client)

        return await self._repository.add(item)

    async def _enrich_from_tmdb(
        self, item: WatchlistItem, tmdb_client: TMDbClient
    ) -> None:
        info = await tmdb_client.search(item.title, item.media_type)
        if info is None:
            return

        # Каноническое название с постера лучше пользовательской фразы:
        # «Одиссея Нолана» на полке выглядит как опечатка, «Одиссея» —
        # как карточка фильма. Исходная формулировка не теряется: по ней
        # и нашли, а год рядом снимает двусмысленность.
        item.title = info.title
        item.poster_url = info.poster_url
        item.overview = info.overview
        item.release_year = info.release_year
        item.tmdb_id = info.tmdb_id

    async def _enrich_from_books(
        self, item: WatchlistItem, books_client: GoogleBooksClient
    ) -> None:
        info = await books_client.search(item.title)
        if info is None:
            return

        item.title = info.title
        item.poster_url = info.thumbnail_url
        item.release_year = info.published_year
        # Автор для книги — самое полезное после названия, а отдельной
        # колонки под него нет: ставим первой строкой описания, где он
        # и читается естественно.
        parts = [p for p in (info.authors, info.description) if p]
        item.overview = " — ".join(parts) if parts else None

    async def list_active_items(self, telegram_user_id: int) -> list[WatchlistItem]:
        return await self._repository.list_by_user(telegram_user_id, status=TO_WATCH)

    async def list_all_items(self, telegram_user_id: int) -> list[WatchlistItem]:
        """to_watch и done вместе — для "полки" в /ui (см. app/watchlist/api.py):
        нужно видеть и что ещё предстоит, и что уже посмотрено/прочитано."""
        return await self._repository.list_by_user(telegram_user_id, status=None)

    async def mark_done(
        self, telegram_user_id: int, item_id: int
    ) -> Optional[WatchlistItem]:
        item = owned_or_none(
            await self._repository.get_by_id(item_id), telegram_user_id
        )
        if item is None:
            return None
        item.status = DONE
        item.completed_at = datetime.now(timezone.utc)
        return await self._repository.save(item)

    async def delete_item(
        self, telegram_user_id: int, item_id: int
    ) -> Optional[WatchlistItem]:
        item = owned_or_none(
            await self._repository.get_by_id(item_id), telegram_user_id
        )
        if item is None:
            return None
        await self._repository.delete(item)
        return item

    async def pick_recommendation(
        self, telegram_user_id: int, ai_client: AIClient | None = None
    ) -> Optional[str]:
        """None — смотреть нечего (пустой список). Иначе — готовая фраза
        с выбранным названием; с AI — плюс короткий комментарий, без AI
        (или при его ошибке) — просто название."""
        items = await self.list_active_items(telegram_user_id)
        if not items:
            return None

        chosen = random.choice(items)
        base = f"Как насчёт «{chosen.title}»?"
        if ai_client is None:
            return base

        comment = await self._generate_comment(ai_client, items, chosen)
        return f"{base} {comment}" if comment else base

    async def _generate_comment(
        self,
        ai_client: AIClient,
        items: list[WatchlistItem],
        chosen: WatchlistItem,
    ) -> str | None:
        listing = "\n".join(f"- {item.title}" for item in items)
        user_content = f"Список:\n{listing}\n\nВыбрано: {chosen.title}"
        messages = [
            {"role": "system", "content": _RECOMMENDATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        try:
            comment = await ai_client.complete(messages)
        except AIServiceError as exc:
            logger.warning("AI-комментарий к рекомендации не сгенерирован: %s", exc)
            return None
        return comment.strip() or None
