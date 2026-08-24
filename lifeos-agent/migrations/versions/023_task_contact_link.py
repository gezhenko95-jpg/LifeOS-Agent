"""tasks: link to a CRM contact

Связь "человек ↔ задача" (specs/022-tasks-v2.md продолжение, п.23
бэклога 23-24.08). ON DELETE SET NULL, не CASCADE — удаление контакта
не должно утаскивать за собой задачи, только снять привязку.

Revision ID: 023_task_contact_link
Revises: 022_tasks_v2
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023_task_contact_link"
down_revision: Union[str, None] = "022_tasks_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "contact_id",
            sa.Integer(),
            nullable=True,
            comment="Связанный контакт CRM (NULL — не связана)",
        ),
    )
    op.create_index(op.f("ix_tasks_contact_id"), "tasks", ["contact_id"])
    op.create_foreign_key(
        "fk_tasks_contact_id_contacts",
        "tasks",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_tasks_contact_id_contacts", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_contact_id"), table_name="tasks")
    op.drop_column("tasks", "contact_id")
