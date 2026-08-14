"""
Минимальный модуль для работы с асинхронными сессиями базы данных
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

# echo печатает каждый SQL вместе с параметрами — а параметры это тексты
# дневниковых записей. На проде это утечка личных данных в логи
# контейнера и лишний оверхед на форматирование строк в горячем пути
# (см. AUDIT.md, C-5).
#
# Выключено по умолчанию и включается ЯВНО через sql_echo=true в .env —
# не через environment: забыть выставить environment=production легче,
# чем осознанно включить отладку, а цена забывчивости здесь — приватные
# записи в логах.
engine = create_async_engine(
    _settings.database_url,
    echo=_settings.sql_echo,
)

# Создаем session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """
    Dependency для получения асинхронной сессии
    """
    async with AsyncSessionLocal() as session:
        yield session
