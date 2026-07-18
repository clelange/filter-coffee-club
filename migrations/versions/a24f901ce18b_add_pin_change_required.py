"""add required PIN change state

Revision ID: a24f901ce18b
Revises: 7711da448462
Create Date: 2026-07-18 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a24f901ce18b"
down_revision: str | Sequence[str] | None = "7711da448462"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "pin_change_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("profiles", "pin_change_required")
