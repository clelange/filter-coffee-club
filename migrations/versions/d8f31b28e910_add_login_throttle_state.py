"""add persistent login throttle state

Revision ID: d8f31b28e910
Revises: a24f901ce18b
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f31b28e910"
down_revision: str | Sequence[str] | None = "a24f901ce18b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "profiles",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column("login_blocked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profiles", "login_blocked_until")
    op.drop_column("profiles", "last_failed_login_at")
    op.drop_column("profiles", "failed_login_attempts")
