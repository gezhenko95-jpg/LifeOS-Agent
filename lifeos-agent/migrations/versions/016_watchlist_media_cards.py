"""add poster and description to watchlist items

Полка перестаёт быть списком голых названий: у записи появляются обложка,
краткое описание и год (см. app/watchlist/tmdb.py). Все поля nullable —
источник внешний и необязательный: без ключа TMDb, без сети или без
совпадения запись живёт ровно как раньше.

Revision ID: 016_watchlist_media
Revises: 015_habit_details
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_watchlist_media"
down_revision: Union[str, None] = "015_habit_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "watchlist_items", sa.Column("poster_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "watchlist_items", sa.Column("overview", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "watchlist_items", sa.Column("release_year", sa.Integer(), nullable=True)
    )
    op.add_column("watchlist_items", sa.Column("tmdb_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("watchlist_items", "tmdb_id")
    op.drop_column("watchlist_items", "release_year")
    op.drop_column("watchlist_items", "overview")
    op.drop_column("watchlist_items", "poster_url")
