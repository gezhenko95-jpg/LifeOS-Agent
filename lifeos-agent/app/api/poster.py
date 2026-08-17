"""
Прокси обложек TMDb.

Зачем. Постеры лежат на `image.tmdb.org`, и до него должен дотянуться
БРАУЗЕР пользователя, а не сервер: из России этот CDN стабильно не
открывается, и на полке вместо обложки получается битая картинка. Сервер
в Нидерландах его видит прекрасно — значит, пусть картинку забирает он.

Аутентификации здесь намеренно нет, в отличие от остального API
(app/api/deps.py): в запрос не входят ни telegram_user_id, ни id записи —
только путь к публичной картинке на CDN. Раскрывать через этот эндпоинт
нечего, а <img> всё равно не умеет слать заголовок X-API-Token.

Открытым прокси он при этом не становится: размер берётся из белого
списка, имя файла обязано выглядеть как имя файла TMDb, и ходим мы
всегда на один-единственный захардкоженный хост.
"""

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["poster"])

_TMDB_IMAGE_HOST = "https://image.tmdb.org/t/p"
# Размеры, которые реально использует app/watchlist/tmdb.py, плюс запас
# на будущее. Белый список, а не любая строка: иначе путь можно увести
# куда угодно через ../.
_ALLOWED_SIZES = {"w92", "w154", "w185", "w342", "w500", "original"}
_FILENAME = re.compile(r"^[A-Za-z0-9]{8,64}\.(jpg|jpeg|png|webp)$")
_TIMEOUT = 15.0
# Постеры не меняются: неделя в кеше браузера снимает повторные запросы
# к нам почти полностью.
_CACHE_CONTROL = "public, max-age=604800, immutable"


@router.get("/poster/{size}/{filename}")
async def get_poster(size: str, filename: str) -> Response:
    if size not in _ALLOWED_SIZES or not _FILENAME.match(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    url = f"{_TMDB_IMAGE_HOST}/{size}/{filename}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            upstream = await http.get(url)
            upstream.raise_for_status()
    except httpx.HTTPError as exc:
        # 404 вместо 502: для <img> разницы нет, а в логах видно, что
        # именно не получилось.
        logger.warning("Обложка %s не получена: %s", url, exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": _CACHE_CONTROL},
    )
