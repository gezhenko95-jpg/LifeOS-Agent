"""
Общая база для доменных репозиториев (tasks/memory/habits/goals/watchlist).

`add`/`get_by_id`/`save`/`delete` были дословно продублированы во всех
пяти — см. AUDIT.md, раздел 4 "Дублирование кода". Домен-специфичные
методы (`list_by_user`, `find_active_by_title`, ...) здесь не место —
у каждого домена свои поля фильтрации, дженерик под них не подходит.
"""

from typing import Generic, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


def escape_like(text: str) -> str:
    """Экранировать %, _ и сам escape-символ — иначе ILIKE-поиск по
    строке, содержащей %, вёл бы себя как SQL-паттерн, а не как
    буквальная подстрока. Раньше была продублирована дословно в
    tasks/memory/habits (habits — с комментарием "не переиспользуется
    ради избежания циклического импорта между доменами"; отсюда, из
    app/core, импортировать безопасно — core не зависит ни от одного
    домена)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class BaseRepository(Generic[ModelT]):
    """Наследник должен задать `model` — класс модели SQLAlchemy.

    ВАЖНЫЙ ИНВАРИАНТ (см. AUDIT.md, A-2): один `AsyncSession` нередко
    держат сразу несколько сервисов одновременно (см.
    app/core/container.py::build_engine — 5 сервисов на одной сессии).
    Любой `save()`/`add()`/`delete()` коммитит ВСЮ сессию целиком,
    включая незакоммиченные изменения ЧУЖИХ объектов, о которых
    вызывающий код может не подозревать. Правило: мутация объекта и
    вызов `save()`/`add()` для него всегда идут подряд, без `await`
    между ними — не мутируйте объект A, потом делайте `await` чего-то
    ещё (в том числе операции над объектом B), потом сохраняйте A.
    Проверено (2026-08-16): весь код в проекте на данный момент этому
    следует. Нарушение — тихий баг: втихую закоммитится наполовину
    готовое состояние соседнего объекта.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: int) -> Optional[ModelT]:
        return await self._session.get(self.model, entity_id)

    async def save(self, entity: ModelT) -> ModelT:
        """Сохранить изменения существующей сущности (update)."""
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.commit()
