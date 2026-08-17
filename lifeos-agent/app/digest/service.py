"""
Digest Service.

Вся бизнес-логика дайджестов Telegram-каналов (см.
specs/013-channel-digests.md): создание темы, добавление/удаление
каналов, сборка текста дайджеста из новых постов.
"""

import logging
from typing import Optional

from app.ai.client import AIClient, AIServiceError
from app.core.ownership import owned_or_none
from app.digest.models import Digest, DigestChannel
from app.digest.repository import DigestRepository
from app.digest.scraper import ChannelPost, ChannelScrapeError, ChannelScraper

logger = logging.getLogger(__name__)

DAILY = "daily"
WEEKLY = "weekly"
_VALID_FREQUENCIES = {None, DAILY, WEEKLY}

_MAX_NAME_LENGTH = 50
_MAX_CHANNEL_LENGTH = 64

# Сколько символов постов отдаём модели: случайно активный канал за сутки
# может выдать десятки тысяч символов, и без обрезки один прогон
# дайджеста разгонял бы счёт токенов на порядок.
_MAX_AI_INPUT_CHARS = 6000

# Длина строки поста в СЫРОМ списке (фолбэк без AI) — телеграм-сообщение
# на десяток каналов иначе не влезает в лимит.
_RAW_SNIPPET_CHARS = 200

_SUMMARY_SYSTEM_PROMPT = (
    "Ты — личный ассистент пользователя. Ниже новые посты из Telegram-"
    "каналов, за которыми он следит по одной теме. Напиши короткое (не "
    "более 150 слов) саммари на русском: сгруппируй по темам, буллетами, "
    "только суть — без предисловий, без кавычек и markdown. Если посты не "
    "связаны между собой, просто перечисли главное из каждого."
)


class DigestService:
    def __init__(self, repository: DigestRepository, scraper: ChannelScraper) -> None:
        self._repository = repository
        self._scraper = scraper

    async def create_digest(
        self,
        telegram_user_id: int,
        name: str,
        auto_frequency: Optional[str] = None,
    ) -> Digest:
        name = name.strip()
        if not name:
            raise ValueError("Имя дайджеста не может быть пустым")
        if len(name.split()) > 1:
            # Имена — один токен: команды разбирают context.args по
            # словам, иначе «/digest_add моя тема канал» неоднозначно.
            raise ValueError("Имя дайджеста должно быть одним словом, без пробелов")
        if len(name) > _MAX_NAME_LENGTH:
            raise ValueError(f"Имя длиннее {_MAX_NAME_LENGTH} символов")
        if auto_frequency not in _VALID_FREQUENCIES:
            raise ValueError(f"Неизвестная частота: {auto_frequency}")

        existing = await self._repository.get_by_name(telegram_user_id, name)
        if existing is not None:
            raise ValueError(f"Дайджест «{name}» уже есть")

        digest = Digest(
            telegram_user_id=telegram_user_id,
            name=name,
            auto_frequency=auto_frequency,
        )
        return await self._repository.add(digest)

    async def list_digests(self, telegram_user_id: int) -> list[Digest]:
        return await self._repository.list_by_user(telegram_user_id)

    async def list_channels(self, digest_id: int) -> list[DigestChannel]:
        return await self._repository.list_channels(digest_id)

    async def get_digest(
        self, telegram_user_id: int, digest_id: int
    ) -> Optional[Digest]:
        """Дайджест по id — для inline-кнопок меню (в callback_data влезает
        id, но не имя: имя может быть кириллическим и до 50 символов, а
        лимит Telegram — 64 БАЙТА на всю строку). Чужой id неотличим от
        несуществующего (owned_or_none, тот же принцип, что везде)."""
        return owned_or_none(
            await self._repository.get_by_id(digest_id), telegram_user_id
        )

    async def remove_channel_by_id(
        self, telegram_user_id: int, channel_id: int
    ) -> Optional[Digest]:
        """Убрать канал, выбранный кнопкой. Возвращает родительский
        дайджест (вызывающему коду нужно перерисовать его экран) или None,
        если канала нет или он чужой — владелец проверяется через
        родительский Digest, у самого канала поля telegram_user_id нет."""
        channel = await self._repository.get_channel_by_id(channel_id)
        if channel is None:
            return None
        digest = await self.get_digest(telegram_user_id, channel.digest_id)
        if digest is None:
            return None
        await self._repository.remove_channel(channel)
        return digest

    async def add_channel(
        self, telegram_user_id: int, digest_name: str, channel_username: str
    ) -> DigestChannel:
        digest = await self._owned_digest(telegram_user_id, digest_name)
        channel_username = normalize_channel_username(channel_username)

        existing = await self._repository.get_channel(digest.id, channel_username)
        if existing is not None:
            raise ValueError(f"@{channel_username} уже в дайджесте «{digest.name}»")

        # Один пробный fetch ДО сохранения: сказать "канал не найден"
        # сразу, а не молчать до следующего дайджеста.
        posts = await self._scraper.fetch_new_posts(channel_username)

        channel = await self._repository.add_channel(digest.id, channel_username)
        # Watermark сразу на самый свежий пост — иначе первый же дайджест
        # после добавления вывалит всю видимую историю канала разом.
        await self._repository.update_last_seen_post_id(channel, posts[-1].post_id)
        return channel

    async def remove_channel(
        self, telegram_user_id: int, digest_name: str, channel_username: str
    ) -> bool:
        digest = await self._owned_digest(telegram_user_id, digest_name)
        channel = await self._repository.get_channel(
            digest.id, normalize_channel_username(channel_username)
        )
        if channel is None:
            return False
        await self._repository.remove_channel(channel)
        return True

    async def build_digest_text(
        self,
        telegram_user_id: int,
        digest_name: str,
        ai_client: AIClient | None = None,
    ) -> Optional[str]:
        """None — новых постов нет (вызывающий код не шлёт пустое
        сообщение, как send_monthly_insights_job)."""
        digest = await self._owned_digest(telegram_user_id, digest_name)
        channels = await self._repository.list_channels(digest.id)

        posts: list[ChannelPost] = []
        for channel in channels:
            posts.extend(await self._collect_new_posts(channel))

        if not posts:
            return None

        header = f"📰 Дайджест «{digest.name}»"
        body = await self._summarize(posts, ai_client)
        return f"{header}\n\n{body}"

    async def _collect_new_posts(self, channel: DigestChannel) -> list[ChannelPost]:
        """Ошибка чтения одного канала не должна ронять весь дайджест —
        остальные каналы всё ещё есть что показать (тот же принцип
        "тихий фолбэк", что и у AI везде в проекте). Watermark при
        ошибке не двигаем: те же посты попадут в следующий прогон."""
        try:
            posts = await self._scraper.fetch_new_posts(
                channel.channel_username, channel.last_seen_post_id
            )
        except ChannelScrapeError as exc:
            logger.warning("Канал @%s не прочитан: %s", channel.channel_username, exc)
            return []

        if not posts:
            return []

        # Watermark двигаем СРАЗУ, даже если текст потом не отправится:
        # иначе те же посты придут повторно следующим дайджестом.
        await self._repository.update_last_seen_post_id(channel, posts[-1].post_id)
        return posts

    async def _summarize(
        self, posts: list[ChannelPost], ai_client: AIClient | None
    ) -> str:
        if ai_client is None:
            return _format_raw_posts(posts)

        try:
            summary = await ai_client.complete(
                [
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": _format_posts_for_ai(posts)},
                ]
            )
        except AIServiceError as exc:
            logger.warning("AI-саммари дайджеста не сгенерировано: %s", exc)
            return _format_raw_posts(posts)

        return summary.strip() or _format_raw_posts(posts)

    async def _owned_digest(self, telegram_user_id: int, digest_name: str) -> Digest:
        digest = owned_or_none(
            await self._repository.get_by_name(telegram_user_id, digest_name.strip()),
            telegram_user_id,
        )
        if digest is None:
            raise ValueError(f"Дайджеста «{digest_name}» нет")
        return digest


def normalize_channel_username(raw: str) -> str:
    """`@channel`, `t.me/channel`, `https://t.me/channel/` → `channel`."""
    value = raw.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    for prefix in ("t.me/s/", "t.me/", "telegram.me/", "@"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    value = value.strip("/")
    if not value:
        raise ValueError("Не понял имя канала")
    if len(value) > _MAX_CHANNEL_LENGTH:
        raise ValueError("Слишком длинное имя канала")
    return value


def _format_raw_posts(posts: list[ChannelPost]) -> str:
    lines = []
    for post in posts:
        snippet = post.text
        if len(snippet) > _RAW_SNIPPET_CHARS:
            snippet = snippet[:_RAW_SNIPPET_CHARS].rstrip() + "…"
        lines.append(f"• {snippet} — {post.url}")
    return "\n".join(lines)


def _format_posts_for_ai(posts: list[ChannelPost]) -> str:
    chunks: list[str] = []
    used = 0
    for post in posts:
        chunk = f"{post.text}\n{post.url}"
        if used + len(chunk) > _MAX_AI_INPUT_CHARS:
            break
        chunks.append(chunk)
        used += len(chunk)
    return "\n\n".join(chunks)
