"""
Клиент Google Books — обложки и описания для книг на полке.

Почему именно он. Проверялись два источника:
- Open Library — работает без ключа, но для русских запросов слаб:
  на «Идиот Достоевский» первым отдаёт «The Notebooks for The Idiot», а
  описания хранит по-английски. Для русскоязычного интерфейса не годится.
- Google Books — русские названия, авторы и аннотации на русском.

ВАЖНО (проверено 17.08.2026): анонимный доступ к Google Books больше не
работает — API отвечает 429 с `quota_limit_value: 0`. Нужен ключ; он
бесплатный и создаётся в том же Google Cloud-проекте, что уже заведён
под Drive. Без ключа фича просто выключена, как и обогащение фильмов без
ключа TMDb (см. app/watchlist/tmdb.py) — книга сохраняется текстом.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_API_URL = "https://www.googleapis.com/books/v1/volumes"
_TIMEOUT = 10.0
# Столько же, сколько у фильмов: карточка полки не должна превращаться в
# страницу текста (см. app/watchlist/tmdb.py).
_MAX_OVERVIEW_CHARS = 400
# Больше пяти результатов не нужно: берём первый пригодный, остальные
# только увеличивают ответ.
_MAX_RESULTS = 5


@dataclass(frozen=True)
class BookInfo:
    volume_id: str
    title: str
    authors: Optional[str]
    description: Optional[str]
    thumbnail_url: Optional[str]
    published_year: Optional[int]


class GoogleBooksClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def search(self, query: str) -> Optional[BookInfo]:
        """Первый пригодный результат или None. Исключения наружу не
        выпускаем: обогащение не должно мешать добавить книгу."""
        query = query.strip()
        if not query or not self._api_key:
            return None

        try:
            response = await self._http.get(
                _API_URL,
                params={
                    "q": query,
                    "key": self._api_key,
                    # Русскоязычные издания вперёд — интерфейс русский, и
                    # «Идиот» нужен как «Идиот», а не как «The Idiot».
                    "langRestrict": "ru",
                    "maxResults": _MAX_RESULTS,
                    "printType": "books",
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Google Books недоступен для «%s»: %s", query, exc)
            return None

        for raw in items:
            info = _parse_volume(raw)
            if info is not None:
                return info
        return None


def _parse_volume(raw: dict) -> Optional[BookInfo]:
    volume_id = raw.get("id")
    volume = raw.get("volumeInfo") or {}
    title = (volume.get("title") or "").strip()
    if not volume_id or not title:
        return None

    subtitle = (volume.get("subtitle") or "").strip()
    if subtitle:
        title = f"{title}. {subtitle}"

    authors = ", ".join(volume.get("authors") or []) or None

    description = (volume.get("description") or "").strip() or None
    if description and len(description) > _MAX_OVERVIEW_CHARS:
        description = description[:_MAX_OVERVIEW_CHARS].rstrip() + "…"

    # Обложку строим сами из id, а не берём imageLinks: там ссылка на
    # http со случайным набором параметров, а нам нужен предсказуемый
    # адрес — по нему ходит наш же прокси (см. app/api/poster.py).
    links = volume.get("imageLinks") or {}
    thumbnail = (
        f"https://books.google.com/books/content?id={volume_id}"
        "&printsec=frontcover&img=1&zoom=2"
        if links
        else None
    )

    published = volume.get("publishedDate") or ""
    year = int(published[:4]) if published[:4].isdigit() else None

    return BookInfo(
        volume_id=volume_id,
        title=title,
        authors=authors,
        description=description,
        thumbnail_url=thumbnail,
        published_year=year,
    )


_client: Optional[GoogleBooksClient] = None


def get_books_client() -> Optional[GoogleBooksClient]:
    """Один клиент на процесс (keep-alive, как у остальных). None —
    ключ не задан, обогащение книг выключено."""
    global _client
    if _client is not None:
        return _client

    api_key = get_settings().google_books_api_key
    if not api_key:
        return None

    _client = GoogleBooksClient(api_key, httpx.AsyncClient())
    return _client
