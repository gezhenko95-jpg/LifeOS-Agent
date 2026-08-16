import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Добавляем путь проекта
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.base import Base

# Импортируем модели здесь, чтобы Alembic их увидел
from app.digest.models import Digest, DigestChannel  # noqa: F401
from app.goals.models import Goal  # noqa: F401
from app.habits.models import Habit, HabitLog  # noqa: F401
from app.memory.models import MemoryEntry  # noqa: F401
from app.tasks.models import Task  # noqa: F401

config = context.config
target_metadata = Base.metadata

# Переопределяем sqlalchemy.url настройками.
# Alembic использует синхронный engine, поэтому убираем асинхронный
# драйвер (+asyncpg) из URL — для миграций используется psycopg2.
database_url = str(get_settings().database_url).replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
