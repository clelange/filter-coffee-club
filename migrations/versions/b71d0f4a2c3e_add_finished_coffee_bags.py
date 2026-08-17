"""add finished coffee bags

Revision ID: b71d0f4a2c3e
Revises: 9c17b3e5a204
Create Date: 2026-08-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b71d0f4a2c3e"
down_revision: str | Sequence[str] | None = "9c17b3e5a204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coffees", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("coffees", "finished_at")
