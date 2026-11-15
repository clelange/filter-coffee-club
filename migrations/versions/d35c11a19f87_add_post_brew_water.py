"""add post-brew water

Revision ID: d35c11a19f87
Revises: f8c1d4a6b920
"""

import sqlalchemy as sa
from alembic import op

revision = "d35c11a19f87"
down_revision = "f8c1d4a6b920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brews", sa.Column("post_brew_water_added", sa.Boolean(), nullable=True))
    op.add_column(
        "brews",
        sa.Column(
            "post_brew_water_g",
            sa.Integer(),
            sa.CheckConstraint(
                "post_brew_water_g IS NULL OR "
                "(post_brew_water_added IS TRUE AND post_brew_water_g BETWEEN 1 AND 5000)",
                name="ck_brew_post_brew_water",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("brews", "post_brew_water_g")
    op.drop_column("brews", "post_brew_water_added")
