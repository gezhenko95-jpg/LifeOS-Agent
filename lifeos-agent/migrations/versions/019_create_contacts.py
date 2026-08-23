"""create contacts table

Личный CRM (см. app/crm/, specs/018-personal-crm.md). Одна строка на
контакт; день рождения хранится как месяц+день без года (повторяющаяся
дата для нэджей, не возраст).

Revision ID: 019_create_contacts
Revises: 018_create_transactions
Create Date: 2026-08-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_create_contacts"
down_revision: Union[str, None] = "018_create_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("birthday_month", sa.Integer(), nullable=True),
        sa.Column("birthday_day", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "last_contact_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Личный CRM — контакты (specs/018-personal-crm.md)",
    )
    op.create_index(op.f("ix_contacts_id"), "contacts", ["id"], unique=False)
    op.create_index(
        op.f("ix_contacts_telegram_user_id"), "contacts", ["telegram_user_id"]
    )
    op.create_index(
        op.f("ix_contacts_last_contact_at"), "contacts", ["last_contact_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contacts_last_contact_at"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_telegram_user_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_id"), table_name="contacts")
    op.drop_table("contacts")
