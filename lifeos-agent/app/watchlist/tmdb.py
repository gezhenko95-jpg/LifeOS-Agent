"""
Клиент TMDb — обложки и описания для полки (см. specs/015-media-cards.md).

Зачем внешний источник, а не AI: модель уверенно придумывает несуществующие
описания и в принципе не может дать картинку. TMDb отдаёт и то, и другое,
на русском, по неточному запросу («Одиссея Нолана» → «Одиссея»), и ключ
для личного использования выдаётся бесплатно.

Тихий фолбэк — тот же принцип, что и везде в проекте: нет ключа, нет
сети, ничего не нашлось — запись просто сохраняется текстом, как раньше.
Обогащение никогда не должно мешать добавить фильм на полку.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.themoviedb.org/3"
# w342 — компромисс: на карточке в /ui постер занимает ~120px, но экраны
# бывают ретиновые; оригинал (до 2000px) грузить ради превью незачем.
_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
_TIMEOUT = 10.0
# Описание в карточку идёт целиком, но у некоторых фильмов TMDb хранит
# пересказ на пол-страницы — обрезаем, иначе карточка полки превращается
# в простыню.
_MAX_OVERVIEW_CHARS = 400

_MEDIA_TO_ENDPOINT = {"movie": "movie", "tv": "tv"}


@dataclass(frozen=True)
class MediaInfo:
    """Найденная карточка. `title` — каноническое название из TMDb: на
    полке лучше «Одиссея», чем то, как пользователь её назвал в
    сообщении («Одиссея Нолана»)."""

    tmdb_id: int
    title: str
    overview: Optional[str]
    poster_url: Optional[str]
    release_year: Optional[int]


class TMDbClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def search(
        self, query: str, media_type: str = "movie"
    ) -> Optional[MediaInfo]:
        """Первый (самый релевантный) результат или None.

        Исключения наружу не выпускаем вообще: обогащение — necessity нет,
        а уронить добавление на полку из-за недоступного TMDb недопустимо.
        """
        query = query.strip()
        if not query or not self._api_key:
            return None

        endpoint = _MEDIA_TO_ENDPOINT.get(media_type, "multi")
        try:
            response = await self._http.get(
                f"{_API_BASE}/search/{endpoint}",
                params={
                    "api_key": self._api_key,
                    "language": "ru-RU",
                    "query": query,
                    "include_adult": "false",
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            results = response.json().get("results") or []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TMDb недоступен для «%s»: %s", query, exc)
            return None

        for raw in results:
            info = _parse_result(raw)
            if info is not None:
                return info
        return None


def _parse_result(raw: dict) -> Optional[MediaInfo]:
    """None для мусорных строк выдачи: у /search/multi среди результатов
    попадаются персоны, у которых нет ни названия, ни постера."""
    title = raw.get("title") or raw.get("name")
    tmdb_id = raw.get("id")
    if not title or not tmdb_id:
        return None

    poster_path = raw.get("poster_path")
    overview = (raw.get("overview") or "").strip() or None
    if overview and len(overview) > _MAX_OVERVIEW_CHARS:
        overview = overview[:_MAX_OVERVIEW_CHARS].rstrip() + "…"

    date = raw.get("release_date") or raw.get("first_air_date") or ""
    year = int(date[:4]) if date[:4].isdigit() else None

    return MediaInfo(
        tmdb_id=int(tmdb_id),
        title=title.strip(),
        overview=overview,
        poster_url=f"{_IMAGE_BASE}{poster_path}" if poster_path else None,
        release_year=year,
    )


_client: Optional[TMDbClient] = None


def get_tmdb_client() -> Optional[TMDbClient]:
    """Один клиент на процесс (keep-alive, как у AIClient и скрейпера
    каналов). None — ключ не задан, обогащение выключено."""
    global _client
    if _client is not None:
        return _client

    api_key = get_settings().tmdb_api_key
    if not api_key:
        return None

    _client = TMDbClient(api_key, httpx.AsyncClient())
    return _client
