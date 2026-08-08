"""add coffee creation tokens

Revision ID: ccf0d81e7f42
Revises: 7f3b2c1d9a04
Create Date: 2026-08-08 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ccf0d81e7f42"
down_revision: str | Sequence[str] | None = "7f3b2c1d9a04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coffees", sa.Column("creation_token", sa.String(length=64), nullable=True))
    op.add_column(
        "coffees", sa.Column("creation_request_hash", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_coffees_creation_token"),
        "coffees",
        ["creation_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_coffees_creation_token"), table_name="coffees")
    op.drop_column("coffees", "creation_request_hash")
    op.drop_column("coffees", "creation_token")
