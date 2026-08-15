"""add performance indexes

См. AUDIT.md, P-6. Три места, где единственный индекс на
telegram_user_id/status по отдельности не покрывает реальный запрос:

1. tasks (telegram_user_id, status) — list_active_tasks выполняется на
   КАЖДЫЙ показ списка задач, брифинг, дайджест: WHERE telegram_user_id
   = X AND status = 'active'.
2. tasks — list_due_unreminded (job раз в минуту, см.
   app/telegram/jobs.py::send_task_reminders_job) сканирует ВСЕХ
   пользователей: WHERE status = 'active' AND due_date IS NOT NULL AND
   due_date <= now() AND reminded_at IS NULL. Частичный индекс — не
   индексируем строки, которые условию заведомо не соответствуют
   (завершённые/отменённые задачи, уже напомненные).
3. memory_entries — list_missing_embeddings (job раз в 5 минут, см.
   embed_pending_memories_job) сканирует ВСЕХ пользователей в поисках
   WHERE embedding IS NULL. Частичный индекс: строк с посчитанным
   embedding в разы больше, чем ожидающих, индексировать их бессмысленно.

Revision ID: 012_add_perf_indexes
Revises: 011_add_embedding_to_memory
Create Date: 2026-08-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_perf_indexes"
down_revision: Union[str, None] = "011_add_embedding_to_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_tasks_user_status",
        "tasks",
        ["telegram_user_id", "status"],
    )
    op.create_index(
        "ix_tasks_due_unreminded",
        "tasks",
        ["due_date"],
        postgresql_where=sa.text(
            "status = 'active' AND due_date IS NOT NULL AND reminded_at IS NULL"
        ),
    )
    op.create_index(
        "ix_memory_entries_missing_embedding",
        "memory_entries",
        ["created_at"],
        postgresql_where=sa.text("embedding IS NULL AND archived = false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_entries_missing_embedding", table_name="memory_entries")
    op.drop_index("ix_tasks_due_unreminded", table_name="tasks")
    op.drop_index("ix_tasks_user_status", table_name="tasks")
