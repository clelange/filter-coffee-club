"""add brew target ratio

Revision ID: e2a4c6d8f901
Revises: b71d0f4a2c3e
Create Date: 2026-08-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a4c6d8f901"
down_revision: str | Sequence[str] | None = "b71d0f4a2c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brews", sa.Column("target_ratio", sa.Float(), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE brews SET target_ratio = water_g / dose_g"))
    with op.batch_alter_table("brews") as batch_op:
        batch_op.alter_column("target_ratio", existing_type=sa.Float(), nullable=False)
        batch_op.create_check_constraint("ck_brew_target_ratio_positive", "target_ratio > 0")


def downgrade() -> None:
    with op.batch_alter_table("brews") as batch_op:
        batch_op.drop_constraint("ck_brew_target_ratio_positive", type_="check")
        batch_op.drop_column("target_ratio")
