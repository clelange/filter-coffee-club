"""add brewing logo

Revision ID: f4a1b2c3d4e5
Revises: e2a4c6d8f901
Create Date: 2026-08-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e2a4c6d8f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_BREWING_LOGO_PATH = "/brand/filter-coffee-club-brewing.svg"


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "brewing_logo_path",
            sa.String(length=500),
            nullable=True,
            server_default=DEFAULT_BREWING_LOGO_PATH,
        ),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE app_settings SET brewing_logo_path = NULL WHERE logo_path IS NOT NULL")
    )


def downgrade() -> None:
    op.drop_column("app_settings", "brewing_logo_path")
