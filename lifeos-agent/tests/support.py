"""
Общие тестовые помощники.

sqlite_engine() — SQLite в памяти для интеграционных тестов репозиториев,
с регистронезависимым сравнением, которое реально понимает кириллицу.

Зачем это нужно: SQLite и его встроенная функция lower() по умолчанию
регистронезависимы только для ASCII — 'Молоко'.lower() в Python даёт
'молоко', а SQLite lower('Молоко') возвращает 'Молоко' без изменений.
ILIKE (см. app/tasks/repository.py, app/memory/repository.py,
app/habits/repository.py) компилируется SQLAlchemy на SQLite именно
через lower(), поэтому без переопределения тесты с русским текстом
(весь проект на русском) либо ломались бы, либо — хуже — молча
проходили бы, ничего не проверив.

Проверено, что это не «подгонка теста под желаемый ответ», а отражение
реального поведения прода: `SELECT 'Молоко' ILIKE '%молоко%'` на боевом
Postgres (server_encoding UTF8) возвращает true — регистронезависимый
кириллический поиск в проде действительно работает, просто тестовая
СУБД (SQLite) сама по себе на такое не способна без этого хука.
"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _unicode_lower(value: str | None) -> str | None:
    return value.lower() if value is not None else None


def sqlite_engine(url: str = "sqlite+aiosqlite:///:memory:") -> AsyncEngine:
    engine = create_async_engine(url)

    @event.listens_for(engine.sync_engine, "connect")
    def _register_unicode_lower(dbapi_connection, connection_record):
        dbapi_connection.create_function("lower", 1, _unicode_lower)

    return engine
