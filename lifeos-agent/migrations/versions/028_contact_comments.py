"""create contact_comments table

Комментарии к контакту CRM — прямая копия task_comments (отчёт
владельца 24.08, вечер #6, волна 3: "добавлять доп. коменты как
подзадачи" у людей).

Revision ID: 028_contact_comments
Revises: 027_task_in_progress_started_at
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028_contact_comments"
down_revision: Union[str, None] = "027_task_in_progress_started_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contact_comments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "contact_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_contact_comments_id"), "contact_comments", ["id"])
    op.create_index(
        op.f("ix_contact_comments_contact_id"), "contact_comments", ["contact_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contact_comments_contact_id"), table_name="contact_comments")
    op.drop_index(op.f("ix_contact_comments_id"), table_name="contact_comments")
    op.drop_table("contact_comments")
