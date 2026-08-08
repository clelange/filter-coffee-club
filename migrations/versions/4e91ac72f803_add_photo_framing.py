"""add photo framing

Revision ID: 4e91ac72f803
Revises: ccf0d81e7f42
Create Date: 2026-08-08 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e91ac72f803"
down_revision: str | Sequence[str] | None = "ccf0d81e7f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("coffees", "grinders", "drippers", "filters")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("photo_focus_x", sa.Float(), nullable=True))
        op.add_column(table, sa.Column("photo_focus_y", sa.Float(), nullable=True))
        op.add_column(table, sa.Column("photo_zoom", sa.Float(), nullable=True))


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "photo_zoom")
        op.drop_column(table, "photo_focus_y")
        op.drop_column(table, "photo_focus_x")
