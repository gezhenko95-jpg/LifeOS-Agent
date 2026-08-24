"""tasks v2: in_progress, subtasks, comments

Три довеска к задачам за один заход (specs/022-tasks-v2.md):
- tasks.in_progress (bool) — статус "в работе", ОРТОГОНАЛЬНЫЙ
  lifecycle-полю tasks.status (active/completed/cancelled). Отдельная
  колонка, а не третье значение status: иначе пришлось бы переписывать
  каждый запрос вида status == "active" (напоминания, дайджест,
  find_active_by_title) на "status в {active, in_progress}" — риск
  тихо сломать существующее поведение ради UI-флажка.
- tasks.parent_id — self-FK, подзадачи/эпики это одна и та же
  механика: "большая задача" — просто задача с детьми, отдельного
  типа не завели. ON DELETE CASCADE — удаление родителя удаляет и
  подзадачи, иначе они осиротеют молча.
- task_comments — лог комментариев к задаче (не одна перезаписываемая
  заметка, а несколько записей с датой).

Revision ID: 022_tasks_v2
Revises: 021_create_assistant_settings
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_tasks_v2"
down_revision: Union[str, None] = "021_create_assistant_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tasks",
        sa.Column(
            "in_progress",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment='Отметка "в работе" — независима от lifecycle-статуса',
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "parent_id",
            sa.Integer(),
            nullable=True,
            comment="Родительская задача (подзадача/эпик), NULL — верхний уровень",
        ),
    )
    op.create_index(op.f("ix_tasks_parent_id"), "tasks", ["parent_id"])
    op.create_foreign_key(
        "fk_tasks_parent_id_tasks",
        "tasks",
        "tasks",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "task_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Лог комментариев к задаче (specs/022-tasks-v2.md)",
    )
    op.create_index(op.f("ix_task_comments_id"), "task_comments", ["id"])
    op.create_index(op.f("ix_task_comments_task_id"), "task_comments", ["task_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_task_comments_task_id"), table_name="task_comments")
    op.drop_index(op.f("ix_task_comments_id"), table_name="task_comments")
    op.drop_table("task_comments")

    op.drop_constraint("fk_tasks_parent_id_tasks", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_parent_id"), table_name="tasks")
    op.drop_column("tasks", "parent_id")
    op.drop_column("tasks", "in_progress")
