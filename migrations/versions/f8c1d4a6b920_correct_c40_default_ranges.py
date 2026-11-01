"""Reduce bundled Comandante C40 reference ranges by six clicks."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c1d4a6b920"
down_revision: str | Sequence[str] | None = "e7b4c2d9a610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Freeze the previous defaults here; future seed changes must not affect upgrades.
PREVIOUS_RANGES = (
    ("Light washed / floral / acidic", 28, 31),
    ("Light natural / fruity", 29, 33),
    ("Medium washed / balanced", 30, 34),
    ("Medium natural / anaerobic", 31, 35),
    ("Chocolate / nutty medium-dark", 32, 35),
    ("Dark roast", 33, 36),
    ("Old / faded beans", 30, 34),
)


def upgrade() -> None:
    connection = op.get_bind()
    for name, old_min, old_max in PREVIOUS_RANGES:
        values = {"name": name, "old_min": old_min, "old_max": old_max}
        # Match both endpoints so customized and already-corrected ranges survive.
        preset_id = connection.scalar(
            sa.text(
                """
                SELECT id FROM recipe_presets
                WHERE name = :name
                  AND reference_setting_min = :old_min
                  AND reference_setting_max = :old_max
                """
            ),
            values,
        )
        if preset_id is None:
            continue
        values["preset_id"] = preset_id
        connection.execute(
            sa.text(
                """
                UPDATE recipe_presets
                SET reference_setting_min = :old_min - 6,
                    reference_setting_max = :old_max - 6,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :preset_id
                """
            ),
            values,
        )
        # Keep matching legacy C40 rows consistent; custom grinder ranges and
        # recorded brews retain their independently entered settings.
        connection.execute(
            sa.text(
                """
                UPDATE preset_grinder_ranges
                SET setting_min = :old_min - 6, setting_max = :old_max - 6
                WHERE preset_id = :preset_id
                  AND setting_min = :old_min AND setting_max = :old_max
                  AND grinder_id IN (
                      SELECT id FROM grinders WHERE definition_key = 'comandante_c40'
                  )
                """
            ),
            values,
        )


def downgrade() -> None:
    # Corrected defaults cannot be distinguished from administrator choices.
    pass
