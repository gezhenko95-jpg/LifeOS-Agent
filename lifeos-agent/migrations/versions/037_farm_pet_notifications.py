"""add notification dedup columns to farm_plots and pets

Бот-уведомления фермы/питомца (specs/028-farm-tamagotchi-rewards.md) —
единственный оставшийся пункт спеки. Тот же приём, что у фокус-сессий
(work_notified_at/break_notified_at, миграция 026): опрашивающая джоба
должна отличать "уже отправлено" от "ещё нет", не полагаясь на
in-memory состояние (бот и API — разные процессы).

farm_plots.ready_notified_at: NULL до первого уведомления, ставится
один раз при отправке "сено готово" — грядка не может "перерасти"
готовность и получить второе уведомление о том же созревании.

pets.hungry_notified_at: НЕ сбрасывается явно при кормлении (append-
only философия остального проекта) — джоба сама сравнивает это поле с
last_fed_at: если кормление случилось ПОСЛЕ последнего уведомления,
значит текущий эпизод голода новый, уведомлять можно снова.

Revision ID: 037_farm_pet_notifications
Revises: 036_pets
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "037_farm_pet_notifications"
down_revision: Union[str, None] = "036_pets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "farm_plots",
        sa.Column(
            "ready_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Когда отправлено уведомление 'сено готово', NULL — ещё не было",
        ),
    )
    op.add_column(
        "pets",
        sa.Column(
            "hungry_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Когда отправлено уведомление 'питомец проголодался'; "
            "сравнивается с last_fed_at, а не сбрасывается при кормлении",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pets", "hungry_notified_at")
    op.drop_column("farm_plots", "ready_notified_at")
