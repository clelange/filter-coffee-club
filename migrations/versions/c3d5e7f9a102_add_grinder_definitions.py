"""Add grinder definitions and C40 reference preset ranges."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a102"
down_revision: str | Sequence[str] | None = "ab12cd34ef56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "grinders",
        sa.Column("definition_key", sa.String(length=64), nullable=False, server_default="custom"),
    )
    op.add_column("recipe_presets", sa.Column("reference_setting_min", sa.Float(), nullable=True))
    op.add_column("recipe_presets", sa.Column("reference_setting_max", sa.Float(), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE grinders
            SET definition_key = 'comandante_c40'
            WHERE lower(trim(manufacturer)) = 'comandante'
              AND lower(trim(model)) IN ('c40', 'c40 mk3', 'c40 mk4')
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE grinders
            SET definition_key = 'kingrinder_k6'
            WHERE lower(trim(manufacturer)) = 'kingrinder'
              AND lower(trim(model)) = 'k6'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE recipe_presets
            SET reference_setting_min = (
                    SELECT ranges.setting_min
                    FROM preset_grinder_ranges AS ranges
                    JOIN grinders ON grinders.id = ranges.grinder_id
                    WHERE ranges.preset_id = recipe_presets.id
                      AND grinders.definition_key = 'comandante_c40'
                    ORDER BY grinders.id
                    LIMIT 1
                ),
                reference_setting_max = (
                    SELECT ranges.setting_max
                    FROM preset_grinder_ranges AS ranges
                    JOIN grinders ON grinders.id = ranges.grinder_id
                    WHERE ranges.preset_id = recipe_presets.id
                      AND grinders.definition_key = 'comandante_c40'
                    ORDER BY grinders.id
                    LIMIT 1
                )
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    known_grinders = connection.execute(
        sa.text(
            """
            SELECT id, definition_key
            FROM grinders
            WHERE definition_key IN ('comandante_c40', 'kingrinder_k6')
            """
        )
    ).all()
    reference_ranges = connection.execute(
        sa.text(
            """
            SELECT id, reference_setting_min, reference_setting_max
            FROM recipe_presets
            WHERE reference_setting_min IS NOT NULL
              AND reference_setting_max IS NOT NULL
            """
        )
    ).all()
    for preset_id, reference_min, reference_max in reference_ranges:
        for grinder_id, definition_key in known_grinders:
            multiplier = Decimal("3.2") if definition_key == "kingrinder_k6" else Decimal("1")

            def legacy_setting(value: float) -> float:
                converted = Decimal(str(value)) * multiplier
                if definition_key == "kingrinder_k6":
                    converted = converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                return float(converted)

            values = {
                "preset_id": preset_id,
                "grinder_id": grinder_id,
                "setting_min": legacy_setting(reference_min),
                "setting_max": legacy_setting(reference_max),
            }
            existing_id = connection.scalar(
                sa.text(
                    """
                    SELECT id
                    FROM preset_grinder_ranges
                    WHERE preset_id = :preset_id AND grinder_id = :grinder_id
                    """
                ),
                values,
            )
            if existing_id is None:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO preset_grinder_ranges (
                            preset_id, grinder_id, setting_min, setting_max
                        ) VALUES (
                            :preset_id, :grinder_id, :setting_min, :setting_max
                        )
                        """
                    ),
                    values,
                )
            else:
                connection.execute(
                    sa.text(
                        """
                        UPDATE preset_grinder_ranges
                        SET setting_min = :setting_min, setting_max = :setting_max
                        WHERE id = :range_id
                        """
                    ),
                    {**values, "range_id": existing_id},
                )

    op.drop_column("recipe_presets", "reference_setting_max")
    op.drop_column("recipe_presets", "reference_setting_min")
    op.drop_column("grinders", "definition_key")
