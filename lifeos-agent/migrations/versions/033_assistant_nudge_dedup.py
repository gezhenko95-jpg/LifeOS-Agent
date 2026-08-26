"""add last_nudge_sent_on/last_nudge_trigger to assistant_settings

Незапланированные сообщения персонажа (specs/027-butler-personas-
phase2.md, п.2) — дедуп в рамках дня, чтобы один и тот же триггер
(например, оборванный стрик) не пришёл дважды на обоих сегодняшних
слотах проверки (midday/evening checkin, см. app/telegram/jobs.py).

Revision ID: 033_assistant_nudge_dedup
Revises: 032_conversation_turns
Create Date: 2026-08-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "033_assistant_nudge_dedup"
down_revision: Union[str, None] = "032_conversation_turns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "assistant_settings",
        sa.Column("last_nudge_sent_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "assistant_settings",
        sa.Column("last_nudge_trigger", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assistant_settings", "last_nudge_trigger")
    op.drop_column("assistant_settings", "last_nudge_sent_on")
