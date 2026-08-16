"""
Репозиторий дайджестов и их каналов.

Единственное место, где выполняются SQL-запросы к таблицам `digests` и
`digest_channels`. Никакой бизнес-логики (нормализация имени канала,
валидация частоты — в service.py).

Каналы живут здесь же, а не в отдельном BaseRepository (по образцу
HabitRepository, где HabitLog тоже без своего репозитория): DigestChannel
доступен только через родительский Digest, самостоятельной жизни у него
нет.
"""

from typing import Optional

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.digest.models import Digest, DigestChannel


class DigestRepository(BaseRepository[Digest]):
    model = Digest

    async def list_by_user(self, telegram_user_id: int) -> list[Digest]:
        query = (
            select(Digest)
            .where(Digest.telegram_user_id == telegram_user_id)
            .order_by(Digest.created_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_name(self, telegram_user_id: int, name: str) -> Optional[Digest]:
        query = select(Digest).where(
            Digest.telegram_user_id == telegram_user_id, Digest.name == name
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def add_channel(self, digest_id: int, channel_username: str) -> DigestChannel:
        channel = DigestChannel(digest_id=digest_id, channel_username=channel_username)
        self._session.add(channel)
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def list_channels(self, digest_id: int) -> list[DigestChannel]:
        query = (
            select(DigestChannel)
            .where(DigestChannel.digest_id == digest_id)
            .order_by(DigestChannel.added_at)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_channel(
        self, digest_id: int, channel_username: str
    ) -> Optional[DigestChannel]:
        query = select(DigestChannel).where(
            DigestChannel.digest_id == digest_id,
            DigestChannel.channel_username == channel_username,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def remove_channel(self, channel: DigestChannel) -> None:
        await self._session.delete(channel)
        await self._session.commit()

    async def update_last_seen_post_id(
        self, channel: DigestChannel, post_id: int
    ) -> None:
        channel.last_seen_post_id = post_id
        await self._session.commit()
