"""add collaborative brew capacity

Revision ID: 432ae1e23fd1
Revises: 4e91ac72f803
Create Date: 2026-08-08 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "432ae1e23fd1"
down_revision: str | Sequence[str] | None = "4e91ac72f803"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("max_active_brews", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "app_settings",
        sa.Column("active_brew_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "brews",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "brew_operators",
        sa.Column("brew_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["brew_id"], ["brews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("brew_id", "profile_id"),
    )
    op.create_index(
        op.f("ix_brew_operators_profile_id"),
        "brew_operators",
        ["profile_id"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO brew_operators (brew_id, profile_id) SELECT id, operator_id FROM brews"
        )
    )
    draft_ids = list(
        connection.execute(
            sa.text("SELECT id FROM brews WHERE status = 'draft' ORDER BY created_at DESC, id DESC")
        ).scalars()
    )
    for brew_id in draft_ids[2:]:
        connection.execute(
            sa.text("UPDATE brews SET status = 'cancelled' WHERE id = :brew_id"),
            {"brew_id": brew_id},
        )
    connection.execute(
        sa.text("UPDATE app_settings SET active_brew_count = :active_count"),
        {"active_count": min(len(draft_ids), 2)},
    )


def downgrade() -> None:
    op.drop_table("brew_operators")
    op.drop_column("brews", "revision")
    op.drop_column("app_settings", "active_brew_count")
    op.drop_column("app_settings", "max_active_brews")
