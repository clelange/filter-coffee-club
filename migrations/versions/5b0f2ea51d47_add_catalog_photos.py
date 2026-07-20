"""add catalog photos

Revision ID: 5b0f2ea51d47
Revises: d8f31b28e910
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b0f2ea51d47"
down_revision: str | Sequence[str] | None = "d8f31b28e910"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coffees", sa.Column("photo_path", sa.String(length=500), nullable=True))
    op.add_column("grinders", sa.Column("photo_path", sa.String(length=500), nullable=True))
    op.add_column("drippers", sa.Column("photo_path", sa.String(length=500), nullable=True))
    op.add_column("filters", sa.Column("photo_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("filters", "photo_path")
    op.drop_column("drippers", "photo_path")
    op.drop_column("grinders", "photo_path")
    op.drop_column("coffees", "photo_path")
