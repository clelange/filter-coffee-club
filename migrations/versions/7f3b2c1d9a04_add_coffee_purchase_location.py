"""add coffee purchase location

Revision ID: 7f3b2c1d9a04
Revises: 5b0f2ea51d47
Create Date: 2026-08-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3b2c1d9a04"
down_revision: str | Sequence[str] | None = "5b0f2ea51d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coffees",
        sa.Column("purchase_location", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coffees", "purchase_location")
