"""
Прокси обложек (см. app/api/poster.py).

Проверяем ровно то, ради чего он существует: браузер ходит на наш домен,
а наружу — только на TMDb и только по разрешённым путям. Сеть мокаем.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

_PATH = "/poster/w342/qA5kPYZA7FkVvqcEfJRoOy4kpHg.jpg"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _upstream(content=b"\xff\xd8jpeg", content_type="image/jpeg", error=None):
    response = MagicMock()
    response.content = content
    response.headers = {"content-type": content_type}
    response.raise_for_status = MagicMock()
    if error is not None:
        response.raise_for_status.side_effect = error

    http = MagicMock()
    http.get = AsyncMock(return_value=response)
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=False)
    return http


def test_poster_is_streamed_from_tmdb(client):
    http = _upstream()
    with patch("app.api.poster.httpx.AsyncClient", return_value=http):
        response = client.get(_PATH)

    assert response.status_code == 200
    assert response.content == b"\xff\xd8jpeg"
    assert http.get.await_args.args[0] == (
        "https://image.tmdb.org/t/p/w342/qA5kPYZA7FkVvqcEfJRoOy4kpHg.jpg"
    )


def test_poster_is_cached_by_browser(client):
    """Постеры не меняются — без длинного кеша каждый показ полки бил бы
    по нашему серверу заново."""
    with patch("app.api.poster.httpx.AsyncClient", return_value=_upstream()):
        response = client.get(_PATH)

    assert "max-age=604800" in response.headers["cache-control"]


def test_poster_needs_no_api_token(client):
    """<img> не умеет слать X-API-Token — если бы эндпоинт требовал
    токен, обложки не грузились бы вообще."""
    with patch("app.api.poster.httpx.AsyncClient", return_value=_upstream()):
        response = client.get(_PATH)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/poster/w999/abcdefgh.jpg",  # размер не из белого списка
        "/poster/w342/short.jpg",  # слишком короткое имя
        "/poster/w342/abcdefgh.svg",  # не картинка из тех, что отдаёт TMDb
        "/poster/w342/abcdefgh.jpg.exe",  # двойное расширение
        "/poster/w342/..%2F..%2Fetc%2Fpasswd",  # попытка выйти из пути
    ],
)
def test_bad_requests_never_go_upstream(client, path):
    http = _upstream()
    with patch("app.api.poster.httpx.AsyncClient", return_value=http):
        response = client.get(path)

    assert response.status_code == 404
    http.get.assert_not_awaited()


def test_unreachable_cdn_gives_404(client):
    """Для <img> разница между 404 и 502 несущественна, а в логах видно,
    что именно не получилось."""
    http = MagicMock()
    http.get = AsyncMock(side_effect=httpx.ConnectError("нет сети"))
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.poster.httpx.AsyncClient", return_value=http):
        response = client.get(_PATH)

    assert response.status_code == 404
