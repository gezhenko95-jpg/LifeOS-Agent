"""
Карточки полки из TMDb: разбор ответа, тихие фолбэки и обогащение записи
(см. app/watchlist/tmdb.py, app/watchlist/service.py).

Сеть не трогаем — мокаем httpx.AsyncClient.get тем же приёмом, что в
tests/ai/test_client.py и tests/digest/test_scraper.py.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.watchlist.models import WatchlistItem
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService
from app.watchlist.tmdb import MediaInfo, TMDbClient

_MOVIE = {
    "id": 1368337,
    "title": "Одиссея",
    "overview": "После Троянской войны Одиссей возвращается домой.",
    "poster_path": "/abc.jpg",
    "release_date": "2026-07-17",
}


def _client(payload=None, status_code=200, raises=None) -> TMDbClient:
    http = MagicMock()
    if raises is not None:
        http.get = AsyncMock(side_effect=raises)
    else:
        response = MagicMock()
        response.json.return_value = payload if payload is not None else {"results": []}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "boom", request=MagicMock(), response=MagicMock()
            )
        http.get = AsyncMock(return_value=response)
    return TMDbClient("test-key", http)


async def test_search_parses_first_result():
    info = await _client({"results": [_MOVIE]}).search("Одиссея Нолана")

    assert info == MediaInfo(
        tmdb_id=1368337,
        title="Одиссея",
        overview="После Троянской войны Одиссей возвращается домой.",
        poster_url="https://image.tmdb.org/t/p/w342/abc.jpg",
        release_year=2026,
    )


async def test_search_asks_tmdb_in_russian():
    client = _client({"results": [_MOVIE]})

    await client.search("Дюна")

    params = client._http.get.await_args.kwargs["params"]
    assert params["language"] == "ru-RU"
    assert params["query"] == "Дюна"


@pytest.mark.parametrize(
    "media_type, expected_endpoint",
    [("movie", "search/movie"), ("tv", "search/tv"), ("other", "search/multi")],
)
async def test_search_endpoint_depends_on_media_type(media_type, expected_endpoint):
    client = _client({"results": [_MOVIE]})

    await client.search("Дюна", media_type)

    assert client._http.get.await_args.args[0].endswith(expected_endpoint)


async def test_result_without_poster_is_still_used():
    """Описание и год ценны сами по себе — не отбрасываем находку из-за
    отсутствующей картинки."""
    info = await _client({"results": [{**_MOVIE, "poster_path": None}]}).search("Дюна")

    assert info.poster_url is None
    assert info.overview


async def test_person_results_are_skipped():
    """У /search/multi в выдаче попадаются персоны — у них нет названия."""
    payload = {"results": [{"id": 5, "name": None, "media_type": "person"}, _MOVIE]}

    info = await _client(payload).search("Нолан", "other")

    assert info.tmdb_id == 1368337


async def test_long_overview_is_trimmed():
    payload = {"results": [{**_MOVIE, "overview": "я" * 900}]}

    info = await _client(payload).search("Дюна")

    assert len(info.overview) <= 401
    assert info.overview.endswith("…")


async def test_missing_date_gives_no_year():
    info = await _client({"results": [{**_MOVIE, "release_date": ""}]}).search("Дюна")

    assert info.release_year is None


async def test_empty_results_return_none():
    assert await _client({"results": []}).search("Такогофильманет") is None


async def test_network_error_returns_none():
    """TMDb недоступен — добавление на полку не должно падать."""
    assert await _client(raises=httpx.ConnectError("нет сети")).search("Дюна") is None


async def test_http_error_returns_none():
    assert await _client(status_code=500).search("Дюна") is None


async def test_empty_key_does_not_call_network():
    client = TMDbClient("", MagicMock(get=AsyncMock()))

    assert await client.search("Дюна") is None
    client._http.get.assert_not_awaited()


# --- Обогащение записи ----------------------------------------------------


@pytest.fixture
def service() -> WatchlistService:
    repository = MagicMock(spec=WatchlistRepository)
    repository.add = AsyncMock(side_effect=lambda item: item)
    return WatchlistService(repository)


async def test_created_item_gets_card(service):
    tmdb = MagicMock()
    tmdb.search = AsyncMock(
        return_value=MediaInfo(1, "Одиссея", "Описание", "https://img/1.jpg", 2026)
    )

    item = await service.create_item(1, "Одиссея Нолана", "movie", tmdb_client=tmdb)

    # Каноническое название с постера вместо пользовательской фразы.
    assert item.title == "Одиссея"
    assert item.poster_url == "https://img/1.jpg"
    assert item.overview == "Описание"
    assert item.release_year == 2026
    assert item.tmdb_id == 1


async def test_item_survives_when_nothing_found(service):
    tmdb = MagicMock()
    tmdb.search = AsyncMock(return_value=None)

    item = await service.create_item(
        1, "Никому не известное кино", "movie", tmdb_client=tmdb
    )

    assert item.title == "Никому не известное кино"
    assert item.poster_url is None


async def test_books_do_not_go_to_tmdb(service):
    """TMDb — про кино; книгу там искать бессмысленно, и лишний запрос
    только тратил бы время на каждое добавление."""
    tmdb = MagicMock()
    tmdb.search = AsyncMock()

    await service.create_item(1, "Идиот", "book", tmdb_client=tmdb)

    tmdb.search.assert_not_awaited()


async def test_without_client_behaves_as_before(service):
    item = await service.create_item(1, "Дюна", "movie")

    assert isinstance(item, WatchlistItem)
    assert item.poster_url is None
