"""crm: tags and per-contact nudge frequency

Довески к CRM (specs/018-personal-crm.md, продолжение) — свободные
теги/группы (одна строка через запятую, не отдельная таблица — ADR-004:
простой код лучше, одному пользователю полноценная модель тегов не
нужна) и своя частота нэджа "давно не писал" вместо глобальных 30 дней
на всех контактов.

Revision ID: 024_crm_tags_nudge
Revises: 023_task_contact_link
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_crm_tags_nudge"
down_revision: Union[str, None] = "023_task_contact_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "contacts",
        sa.Column(
            "tags",
            sa.String(length=200),
            nullable=True,
            comment="Группы/теги через запятую, свободный текст",
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "nudge_after_days",
            sa.Integer(),
            nullable=True,
            comment='Свой порог "давно не писал" в днях (NULL — глобальный дефолт 30)',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("contacts", "nudge_after_days")
    op.drop_column("contacts", "tags")
