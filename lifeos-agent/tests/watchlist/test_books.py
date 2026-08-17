"""
Карточки книг из Google Books (см. app/watchlist/books.py).

Сеть мокаем — тем же приёмом, что и в tests/watchlist/test_tmdb.py.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.watchlist.books import BookInfo, GoogleBooksClient
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService

_VOLUME = {
    "id": "zyTCAlFPjgYC",
    "volumeInfo": {
        "title": "Идиот",
        "authors": ["Фёдор Достоевский"],
        "description": "Князь Мышкин возвращается в Петербург.",
        "publishedDate": "1869-01-01",
        "imageLinks": {
            "thumbnail": "http://books.google.com/books/content?id=zyTCAlFPjgYC"
        },
    },
}


def _client(payload=None, raises=None, api_key="test-key") -> GoogleBooksClient:
    http = MagicMock()
    if raises is not None:
        http.get = AsyncMock(side_effect=raises)
    else:
        response = MagicMock()
        response.json.return_value = payload if payload is not None else {"items": []}
        response.raise_for_status = MagicMock()
        http.get = AsyncMock(return_value=response)
    return GoogleBooksClient(api_key, http)


async def test_search_parses_volume():
    info = await _client({"items": [_VOLUME]}).search("Идиот Достоевский")

    assert info == BookInfo(
        volume_id="zyTCAlFPjgYC",
        title="Идиот",
        authors="Фёдор Достоевский",
        description="Князь Мышкин возвращается в Петербург.",
        thumbnail_url=(
            "https://books.google.com/books/content?id=zyTCAlFPjgYC"
            "&printsec=frontcover&img=1&zoom=2"
        ),
        published_year=1869,
    )


async def test_cover_url_is_https_and_predictable():
    """Google отдаёт ссылку на http и со случайным набором параметров —
    строим адрес сами, по нему потом ходит наш прокси."""
    info = await _client({"items": [_VOLUME]}).search("Идиот")

    assert info.thumbnail_url.startswith("https://")


async def test_russian_editions_are_preferred():
    client = _client({"items": [_VOLUME]})

    await client.search("Идиот")

    assert client._http.get.await_args.kwargs["params"]["langRestrict"] == "ru"


async def test_country_is_always_sent():
    """Без параметра country Google Books отвечает 503 backendFailed —
    поймано на живом ключе, поэтому это не косметика."""
    client = _client({"items": [_VOLUME]})

    await client.search("Идиот")

    assert client._http.get.await_args.kwargs["params"]["country"] == "RU"


async def test_most_complete_volume_wins():
    """Верхний результат Google нередко пустой: на «Идиот Достоевский»
    первым идёт том без автора и аннотации, а нужный — вторым."""
    empty = {"id": "empty1", "volumeInfo": {"title": "Федор Достоевский. Идиот"}}

    info = await _client({"items": [empty, _VOLUME]}).search("Идиот Достоевский")

    assert info.volume_id == "zyTCAlFPjgYC"
    assert info.description


async def test_relevance_order_kept_between_equally_full_volumes():
    """Одинаково полные тома не переставляем — у Google выше стоит более
    релевантный."""
    second = {**_VOLUME, "id": "second"}

    info = await _client({"items": [_VOLUME, second]}).search("Идиот")

    assert info.volume_id == "zyTCAlFPjgYC"


async def test_subtitle_is_added_to_title():
    volume = {
        "id": "abcde",
        "volumeInfo": {**_VOLUME["volumeInfo"], "subtitle": "Роман в четырёх частях"},
    }

    info = await _client({"items": [volume]}).search("Идиот")

    assert info.title == "Идиот. Роман в четырёх частях"


async def test_volume_without_images_has_no_cover():
    volume = {"id": "abcde", "volumeInfo": {"title": "Без обложки"}}

    info = await _client({"items": [volume]}).search("Без обложки")

    assert info.thumbnail_url is None
    assert info.title == "Без обложки"


async def test_volume_without_title_is_skipped():
    payload = {"items": [{"id": "x1", "volumeInfo": {}}, _VOLUME]}

    info = await _client(payload).search("Идиот")

    assert info.volume_id == "zyTCAlFPjgYC"


async def test_long_description_is_trimmed():
    volume = {"id": "abcde", "volumeInfo": {"title": "Том", "description": "я" * 900}}

    info = await _client({"items": [volume]}).search("Том")

    assert len(info.description) <= 401


async def test_nothing_found_returns_none():
    assert await _client({"items": []}).search("Несуществующая книга") is None


async def test_network_error_returns_none():
    assert await _client(raises=httpx.ConnectError("нет сети")).search("Идиот") is None


async def test_without_key_does_not_call_network():
    """Анонимный доступ к Google Books закрыт (429, квота ноль), поэтому
    без ключа даже не пытаемся."""
    client = _client({"items": [_VOLUME]}, api_key="")

    assert await client.search("Идиот") is None
    client._http.get.assert_not_awaited()


# --- Обогащение записи ----------------------------------------------------


@pytest.fixture
def service() -> WatchlistService:
    repository = MagicMock(spec=WatchlistRepository)
    repository.add = AsyncMock(side_effect=lambda item: item)
    return WatchlistService(repository)


async def test_book_gets_card_from_google_books(service):
    books = MagicMock()
    books.search = AsyncMock(
        return_value=BookInfo(
            "v1", "Идиот", "Достоевский", "Описание", "https://c/1", 1869
        )
    )

    item = await service.create_item(1, "идиот", "book", books_client=books)

    assert item.title == "Идиот"
    assert item.poster_url == "https://c/1"
    assert item.release_year == 1869
    # Автора отдельной колонкой не храним — он первым в описании, где и
    # читается естественно.
    assert item.overview == "Достоевский — Описание"


async def test_book_without_author_keeps_plain_description(service):
    books = MagicMock()
    books.search = AsyncMock(
        return_value=BookInfo("v1", "Том", None, "Просто описание", None, None)
    )

    item = await service.create_item(1, "том", "book", books_client=books)

    assert item.overview == "Просто описание"


async def test_movie_does_not_go_to_google_books(service):
    """У каждого типа свой источник: кино ищем в TMDb, книги — здесь."""
    books = MagicMock()
    books.search = AsyncMock()
    tmdb = MagicMock()
    tmdb.search = AsyncMock(return_value=None)

    await service.create_item(1, "Дюна", "movie", tmdb_client=tmdb, books_client=books)

    books.search.assert_not_awaited()
    tmdb.search.assert_awaited_once()


async def test_book_survives_when_nothing_found(service):
    books = MagicMock()
    books.search = AsyncMock(return_value=None)

    item = await service.create_item(1, "Неизвестная книга", "book", books_client=books)

    assert item.title == "Неизвестная книга"
    assert item.poster_url is None
