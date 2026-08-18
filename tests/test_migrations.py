from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import Settings
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    database_path = Path(database_url.removeprefix("sqlite:///"))
    config.attributes["settings"] = Settings(
        database_url=database_url,
        data_dir=database_path.parent,
    )
    config.attributes["skip_logging_config"] = True
    return config


def test_collaborative_brew_migration_backfills_and_limits_legacy_drafts(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    config = alembic_config(database_url)
    command.upgrade(config, "ccf0d81e7f42")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO app_settings (
                    id, app_name, subtitle, public_base_url, logo_path,
                    color_cream, color_surface, color_ink, color_coffee, color_cyan, color_amber
                ) VALUES (
                    1, 'Legacy club', 'Before collaboration', NULL, NULL,
                    '#F6F1E8', '#FFFDFC', '#241C19', '#6B3F2A', '#007F9E', '#D88700'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO profiles (
                    id, display_name, pin_hash, role, active, pin_change_required,
                    failed_login_attempts, created_at, updated_at
                ) VALUES (
                    1, 'Ada', 'legacy-hash', 'admin', 1, 0, 0,
                    '2026-01-01 08:00:00', '2026-01-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO grinders (
                    id, manufacturer, model, setting_unit, setting_step,
                    soft_min, soft_max, guidance, archived, created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Grinder', 'clicks', 1,
                    0, 50, NULL, 0, '2026-01-01 08:00:00', '2026-01-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees (
                    id, roaster, name, archived, created_by_id, created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Coffee', 0, 1,
                    '2026-01-01 08:00:00', '2026-01-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO brews (
                    id, coffee_id, operator_id, grinder_id, dose_g, water_g,
                    temperature_c, grinder_setting, servings, status, created_at, updated_at
                ) VALUES (
                    :id, 1, 1, 1, 15, 240, 94, 30, 1, :status, :created_at, :created_at
                )
                """
            ),
            [
                {"id": 1, "status": "draft", "created_at": "2026-01-01 09:00:00"},
                {"id": 2, "status": "completed", "created_at": "2026-01-01 10:00:00"},
                {"id": 3, "status": "draft", "created_at": "2026-01-01 11:00:00"},
                {"id": 4, "status": "draft", "created_at": "2026-01-01 12:00:00"},
                {"id": 5, "status": "draft", "created_at": "2026-01-01 12:00:00"},
            ],
        )
    engine.dispose()

    command.upgrade(config, "432ae1e23fd1")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        brews = connection.execute(text("SELECT id, status, revision FROM brews ORDER BY id")).all()
        assert brews == [
            (1, "cancelled", 1),
            (2, "completed", 1),
            (3, "cancelled", 1),
            (4, "draft", 1),
            (5, "draft", 1),
        ]
        assert connection.execute(
            text("SELECT brew_id, profile_id FROM brew_operators ORDER BY brew_id")
        ).all() == [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]
        assert connection.execute(
            text("SELECT max_active_brews, active_brew_count FROM app_settings WHERE id = 1")
        ).one() == (2, 2)
        indexes = {item["name"] for item in inspect(connection).get_indexes("brew_operators")}
        assert "ix_brew_operators_profile_id" in indexes
    engine.dispose()


def test_brew_creation_token_migration_preserves_existing_rows(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pre-idempotency.sqlite3'}"
    config = alembic_config(database_url)
    command.upgrade(config, "8f4b0c2a7e16")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profiles (
                    id, display_name, pin_hash, role, active, pin_change_required,
                    failed_login_attempts, created_at, updated_at
                ) VALUES (
                    1, 'Ada', 'legacy-hash', 'admin', 1, 0,
                    0, '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO grinders (
                    id, manufacturer, model, setting_unit, setting_step,
                    archived, created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Grinder', 'clicks', 1,
                    0, '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees (
                    id, roaster, name, chart_color, archived, created_by_id,
                    created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Coffee', '#0072B2', 0, 1,
                    '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO brews (
                    id, coffee_id, operator_id, grinder_id, dose_g, water_g,
                    temperature_c, grinder_setting, servings, status, revision,
                    created_at, updated_at
                ) VALUES (
                    1, 1, 1, 1, 15, 240,
                    94, 30, 1, 'completed', 1,
                    '2026-08-01 09:00:00', '2026-08-01 09:00:00'
                )
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "9c17b3e5a204")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, creation_token, creation_request_hash FROM brews")
        ).one() == (1, None, None)
        indexes = {item["name"]: item for item in inspect(connection).get_indexes("brews")}
        assert indexes["ix_brews_creation_token"]["unique"]
    engine.dispose()


def test_finished_coffee_migration_preserves_existing_availability(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pre-finished-coffees.sqlite3'}"
    config = alembic_config(database_url)
    command.upgrade(config, "9c17b3e5a204")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profiles (
                    id, display_name, pin_hash, role, active, pin_change_required,
                    failed_login_attempts, created_at, updated_at
                ) VALUES (
                    1, 'Ada', 'legacy-hash', 'admin', 1, 0,
                    0, '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees (
                    id, roaster, name, chart_color, archived, created_by_id,
                    created_at, updated_at
                ) VALUES
                    (1, 'Legacy', 'Available', '#0072B2', 0, 1,
                     '2026-08-01 08:00:00', '2026-08-01 08:00:00'),
                    (2, 'Legacy', 'Archived', '#D55E00', 1, 1,
                     '2026-08-01 08:00:00', '2026-08-01 08:00:00')
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "b71d0f4a2c3e")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, archived, finished_at FROM coffees ORDER BY id")
        ).all() == [(1, 0, None), (2, 1, None)]
        columns = {column["name"] for column in inspect(connection).get_columns("coffees")}
        assert "finished_at" in columns
    engine.dispose()


def test_target_ratio_migration_backfills_existing_brews(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pre-target-ratio.sqlite3'}"
    config = alembic_config(database_url)
    command.upgrade(config, "b71d0f4a2c3e")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profiles (
                    id, display_name, pin_hash, role, active, pin_change_required,
                    failed_login_attempts, created_at, updated_at
                ) VALUES (
                    1, 'Ada', 'legacy-hash', 'admin', 1, 0,
                    0, '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO grinders (
                    id, manufacturer, model, setting_unit, setting_step,
                    archived, created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Grinder', 'clicks', 1,
                    0, '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees (
                    id, roaster, name, chart_color, archived, created_by_id,
                    created_at, updated_at
                ) VALUES (
                    1, 'Legacy', 'Coffee', '#0072B2', 0, 1,
                    '2026-08-01 08:00:00', '2026-08-01 08:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO brews (
                    id, coffee_id, operator_id, grinder_id, dose_g, water_g,
                    temperature_c, grinder_setting, servings, status, revision,
                    created_at, updated_at
                ) VALUES (
                    1, 1, 1, 1, 15, 240,
                    94, 30, 1, 'completed', 1,
                    '2026-08-01 09:00:00', '2026-08-01 09:00:00'
                )
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "e2a4c6d8f901")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT target_ratio FROM brews")).scalar_one() == 16
        target_ratio = next(
            column
            for column in inspect(connection).get_columns("brews")
            if column["name"] == "target_ratio"
        )
        assert target_ratio["nullable"] is False
    engine.dispose()


def test_brewing_logo_migration_defaults_existing_installations(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pre-brewing-logo.sqlite3'}"
    config = alembic_config(database_url)
    command.upgrade(config, "e2a4c6d8f901")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO app_settings (
                    id, app_name, subtitle, public_base_url, logo_path,
                    color_cream, color_surface, color_ink, color_coffee, color_cyan, color_amber
                ) VALUES
                    (
                        1, 'Custom club', 'Custom identity', NULL, '/uploads/custom-logo.webp',
                        '#F6F1E8', '#FFFDFC', '#241C19', '#6B3F2A', '#007F9E', '#D88700'
                    ),
                    (
                        2, 'Default club', 'Bundled identity', NULL, NULL,
                        '#F6F1E8', '#FFFDFC', '#241C19', '#6B3F2A', '#007F9E', '#D88700'
                    )
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "f4a1b2c3d4e5")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, logo_path, brewing_logo_path FROM app_settings ORDER BY id")
        ).all() == [
            (1, "/uploads/custom-logo.webp", None),
            (2, None, "/brand/filter-coffee-club-brewing.svg"),
        ]
        brewing_logo = next(
            column
            for column in inspect(connection).get_columns("app_settings")
            if column["name"] == "brewing_logo_path"
        )
        assert brewing_logo["nullable"] is True
    engine.dispose()
