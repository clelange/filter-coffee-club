"""Add an optional name for each brew

Revision ID: 29ba5c31ee41
Revises: d35c11a19f87
"""

import sqlalchemy as sa
from alembic import op

revision = "29ba5c31ee41"
down_revision = "d35c11a19f87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brews", sa.Column("brew_name", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("brews", "brew_name")
