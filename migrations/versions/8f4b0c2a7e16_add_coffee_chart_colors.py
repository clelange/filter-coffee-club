"""add coffee chart colors

Revision ID: 8f4b0c2a7e16
Revises: 432ae1e23fd1
Create Date: 2026-08-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f4b0c2a7e16"
down_revision: str | Sequence[str] | None = "432ae1e23fd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COFFEE_COLOR_PALETTE = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#A6761D",
    "#6A3D9A",
    "#B2182B",
    "#4D4D4D",
)


def upgrade() -> None:
    op.add_column("coffees", sa.Column("chart_color", sa.String(length=7), nullable=True))
    connection = op.get_bind()
    coffee_ids = list(connection.execute(sa.text("SELECT id FROM coffees ORDER BY id")).scalars())
    for index, coffee_id in enumerate(coffee_ids):
        connection.execute(
            sa.text("UPDATE coffees SET chart_color = :color WHERE id = :coffee_id"),
            {
                "color": COFFEE_COLOR_PALETTE[index % len(COFFEE_COLOR_PALETTE)],
                "coffee_id": coffee_id,
            },
        )
    with op.batch_alter_table("coffees") as batch_op:
        batch_op.alter_column("chart_color", existing_type=sa.String(length=7), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("coffees") as batch_op:
        batch_op.drop_column("chart_color")
