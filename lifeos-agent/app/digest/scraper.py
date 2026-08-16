"""
Чтение чужих ПУБЛИЧНЫХ Telegram-каналов через веб-превью
`https://t.me/s/<channel>` (см. specs/013-channel-digests.md).

Почему не MTProto-юзербот (Telethon/Pyrogram): вход под личным
Telegram-аккаунтом означает, что файл сессии равносилен "ещё одно
устройство залогинено в аккаунт" — полный доступ, а не ограниченный
токен, плюс риск ограничений самого аккаунта при нетипичном
API-поведении. Веб-превью — та же страница, что открывается в браузере
без логина, никакой авторизации и никакого риска для аккаунта. Плата за
это — только публичные каналы (ровно случай владельца) и неофициальный,
хоть и стабильный годами, контракт разметки.

Разметка (проверена вживую на https://t.me/s/telegram):
- пост — `div.tgme_widget_message[data-post="channel/12345"]`,
  число после `/` — монотонно растущий id поста;
- текст — `.tgme_widget_message_text.js-message_text`;
- дата — `time[datetime]` внутри `.tgme_widget_message_date`.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://t.me/s"
_POST_URL = "https://t.me"

# Без ретраев, как у AIClient._post_json: дайджест — не критичная
# доставка, следующий прогон и так подхватит пропущенное (watermark
# last_seen_post_id не сдвигается, если чтение не удалось).
_TIMEOUT_SECONDS = 15.0

# t.me отдаёт превью и без него, но браузерный UA снижает риск, что
# запрос примут за бота и ограничат.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class ChannelPost:
    post_id: int
    text: str
    url: str
    published_at: datetime


class ChannelScrapeError(Exception):
    """Канал не найден, приватный, или страница не распозналась."""


class ChannelScraper:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_new_posts(
        self, channel_username: str, after_post_id: int | None = None
    ) -> list[ChannelPost]:
        """Новые посты канала, от старых к новым.

        Читается только первая страница превью (самые свежие посты) —
        пагинация вглубь истории (`?before=<post_id>`) дайджесту не
        нужна. `after_post_id is None` — канал добавляется впервые,
        отдаём всё, что на странице (вызывающий код сразу выставит
        watermark, чтобы не вывалить историю пользователю).
        """
        html = await self._get(channel_username)
        posts = _parse_posts(html, channel_username)
        if not posts:
            raise ChannelScrapeError(
                f"Не удалось прочитать канал @{channel_username} — "
                "не найден, приватный или без постов"
            )
        if after_post_id is None:
            return posts
        return [post for post in posts if post.post_id > after_post_id]

    async def _get(self, channel_username: str) -> str:
        url = f"{_BASE_URL}/{channel_username}"
        try:
            response = await self._http.get(
                url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
            )
        except httpx.HTTPError as exc:
            raise ChannelScrapeError(f"Ошибка сети при чтении {url}: {exc}") from exc

        if response.status_code != 200:
            raise ChannelScrapeError(f"{url} вернул статус {response.status_code}")
        return response.text


def _parse_posts(html: str, channel_username: str) -> list[ChannelPost]:
    # html.parser, а не lxml: пара страниц в день не стоит зависимости
    # от компилируемого C-парсера в докер-образе (ADR-004).
    soup = BeautifulSoup(html, "html.parser")

    posts: list[ChannelPost] = []
    for node in soup.select("div.tgme_widget_message[data-post]"):
        post = _parse_post(node, channel_username)
        if post is not None:
            posts.append(post)

    posts.sort(key=lambda post: post.post_id)
    return posts


def _parse_post(node, channel_username: str) -> ChannelPost | None:
    """None — узел без id/текста/даты (сервисное сообщение, пост из
    одних медиа): пропускаем молча, один такой пост не повод объявлять
    весь канал непрочитанным."""
    post_id = _parse_post_id(node.get("data-post", ""))
    if post_id is None:
        return None

    text_node = node.select_one(".tgme_widget_message_text.js-message_text")
    if text_node is None:
        return None
    text = text_node.get_text(" ", strip=True)
    if not text:
        return None

    published_at = _parse_published_at(node)
    if published_at is None:
        return None

    return ChannelPost(
        post_id=post_id,
        text=text,
        url=f"{_POST_URL}/{channel_username}/{post_id}",
        published_at=published_at,
    )


def _parse_post_id(data_post: str) -> int | None:
    _, _, tail = data_post.rpartition("/")
    try:
        return int(tail)
    except ValueError:
        return None


def _parse_published_at(node) -> datetime | None:
    time_node = node.select_one(".tgme_widget_message_date time[datetime]")
    if time_node is None:
        return None
    try:
        return datetime.fromisoformat(time_node["datetime"])
    except ValueError:
        return None


# Один httpx-клиент на процесс — тот же keep-alive-принцип, что у
# AIClient (см. AUDIT.md, P-4). Отдельный от AIClient._http: другой хост,
# другой таймаут, и пул соединений имеет смысл держать раздельно.
_http_client: httpx.AsyncClient | None = None


def get_channel_scraper() -> ChannelScraper:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    return ChannelScraper(_http_client)
