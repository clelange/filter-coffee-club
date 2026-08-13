"""add brew creation tokens

Revision ID: 9c17b3e5a204
Revises: 8f4b0c2a7e16
Create Date: 2026-08-13 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c17b3e5a204"
down_revision: str | Sequence[str] | None = "8f4b0c2a7e16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brews", sa.Column("creation_token", sa.String(length=64), nullable=True))
    op.add_column("brews", sa.Column("creation_request_hash", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_brews_creation_token"),
        "brews",
        ["creation_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_brews_creation_token"), table_name="brews")
    op.drop_column("brews", "creation_request_hash")
    op.drop_column("brews", "creation_token")
