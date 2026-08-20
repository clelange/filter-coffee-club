"""Improve the default interface palette contrast."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b4c2d9a610"
down_revision: str | Sequence[str] | None = "c3d5e7f9a102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE app_settings
            SET color_cyan = '#00728F'
            WHERE upper(color_cyan) = '#007F9E'
            """
        )
    )


def downgrade() -> None:
    # The upgraded default is indistinguishable from the same value chosen by an
    # administrator, so reverting data here could destroy a custom palette.
    pass
