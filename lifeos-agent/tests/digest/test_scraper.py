"""
ChannelScraper на фиксированном фрагменте реальной разметки t.me/s/
(проверена вживую на https://t.me/s/telegram — см. app/digest/scraper.py).
Сеть мокается тем же способом, что в tests/ai/test_client.py для .post.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.digest.scraper import ChannelScrapeError, ChannelScraper

_PAGE = """
<html><body>
  <div class="tgme_widget_message" data-post="testchannel/100">
    <div class="tgme_widget_message_text js-message_text">
      Первый пост <a href="https://example.com">со ссылкой</a>
    </div>
    <div class="tgme_widget_message_footer">
      <div class="tgme_widget_message_info">
        <a class="tgme_widget_message_date" href="https://t.me/testchannel/100">
          <time datetime="2026-08-16T07:01:44+00:00" class="time">10:01</time>
        </a>
      </div>
    </div>
  </div>
  <div class="tgme_widget_message" data-post="testchannel/101">
    <div class="tgme_widget_message_text js-message_text">Второй пост</div>
    <div class="tgme_widget_message_footer">
      <div class="tgme_widget_message_info">
        <a class="tgme_widget_message_date" href="https://t.me/testchannel/101">
          <time datetime="2026-08-17T09:30:00+00:00" class="time">12:30</time>
        </a>
      </div>
    </div>
  </div>
</body></html>
"""

# Пост без текста (одна картинка) — не должен ронять разбор всей страницы.
_PAGE_WITH_MEDIA_ONLY_POST = """
<html><body>
  <div class="tgme_widget_message" data-post="testchannel/200">
    <div class="tgme_widget_message_photo_wrap"></div>
  </div>
  <div class="tgme_widget_message" data-post="testchannel/201">
    <div class="tgme_widget_message_text js-message_text">Текстовый</div>
    <div class="tgme_widget_message_date">
      <time datetime="2026-08-17T09:30:00+00:00" class="time">12:30</time>
    </div>
  </div>
</body></html>
"""

_EMPTY_PAGE = "<html><body><div class='tgme_page'>Channel not found</div></body></html>"


def _response(status_code: int, text: str = ""):
    request = httpx.Request("GET", "https://t.me/s/testchannel")
    return httpx.Response(status_code, text=text, request=request)


def _scraper() -> ChannelScraper:
    return ChannelScraper(httpx.AsyncClient())


async def test_fetch_new_posts_parses_page():
    with patch(
        "httpx.AsyncClient.get", new=AsyncMock(return_value=_response(200, _PAGE))
    ):
        posts = await _scraper().fetch_new_posts("testchannel")

    assert [post.post_id for post in posts] == [100, 101]
    assert posts[0].text == "Первый пост со ссылкой"
    assert posts[0].url == "https://t.me/testchannel/100"
    assert posts[1].published_at.year == 2026
    assert posts[1].published_at.hour == 9


async def test_fetch_new_posts_filters_by_after_post_id():
    with patch(
        "httpx.AsyncClient.get", new=AsyncMock(return_value=_response(200, _PAGE))
    ):
        posts = await _scraper().fetch_new_posts("testchannel", after_post_id=100)

    assert [post.post_id for post in posts] == [101]


async def test_fetch_new_posts_returns_empty_when_nothing_newer():
    with patch(
        "httpx.AsyncClient.get", new=AsyncMock(return_value=_response(200, _PAGE))
    ):
        posts = await _scraper().fetch_new_posts("testchannel", after_post_id=101)

    assert posts == []


async def test_fetch_new_posts_skips_posts_without_text():
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_response(200, _PAGE_WITH_MEDIA_ONLY_POST)),
    ):
        posts = await _scraper().fetch_new_posts("testchannel")

    assert [post.post_id for post in posts] == [201]


async def test_fetch_new_posts_raises_on_page_without_messages():
    with patch(
        "httpx.AsyncClient.get", new=AsyncMock(return_value=_response(200, _EMPTY_PAGE))
    ):
        with pytest.raises(ChannelScrapeError):
            await _scraper().fetch_new_posts("testchannel")


async def test_fetch_new_posts_raises_on_non_200():
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=_response(404))):
        with pytest.raises(ChannelScrapeError):
            await _scraper().fetch_new_posts("testchannel")


async def test_fetch_new_posts_raises_on_network_error():
    with patch(
        "httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("boom"))
    ):
        with pytest.raises(ChannelScrapeError):
            await _scraper().fetch_new_posts("testchannel")
