"""
Минимальный модуль для работы с асинхронными сессиями базы данных
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# Создаем engine
engine = create_async_engine(
    get_settings().database_url,
    echo=True,  # Для отладки в development
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
