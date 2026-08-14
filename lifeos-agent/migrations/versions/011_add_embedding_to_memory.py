"""add embedding to memory_entries

Семантический поиск по памяти (см. specs/011-semantic-memory-search.md):
JSON, не pgvector (ADR-004 — датасет одного пользователя, косинусное
сходство считается в Python, лишний тип данных/расширение Postgres не
нужны). NULL — ещё не посчитан, доливается фоновой job (см.
app/telegram/jobs.py::embed_pending_memories_job).

Revision ID: 011_add_embedding_to_memory
Revises: 010_create_watchlist_items
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_add_embedding_to_memory"
down_revision: Union[str, None] = "010_create_watchlist_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "memory_entries",
        sa.Column(
            "embedding",
            sa.JSON(),
            nullable=True,
            comment="Вектор embedding для семантического поиска (NULL — ещё не посчитан)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("memory_entries", "embedding")
