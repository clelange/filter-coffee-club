"""Record the water profile used for each brew."""

import sqlalchemy as sa
from alembic import op

revision = "36aa891bd2ea"
down_revision = "29ba5c31ee41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brews",
        sa.Column(
            "water_profile", sa.JSON(), nullable=False, server_default='{"preset":"Tap water"}'
        ),
    )


def downgrade() -> None:
    op.drop_column("brews", "water_profile")
