from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import Settings
from sqlalchemy import create_engine, inspect, text

from tests.api_helpers import PROJECT_ROOT


def test_coffee_chart_color_migration_backfills_existing_rows(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.sqlite3'}"
    project_root = PROJECT_ROOT
    config = Config(project_root / "alembic.ini")
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["skip_logging_config"] = True
    config.attributes["settings"] = Settings(data_dir=tmp_path, database_url=database_url)
    command.upgrade(config, "5b0f2ea51d47")

    engine = create_engine(database_url)
    now = "2026-08-08 00:00:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profiles
                    (id, display_name, pin_hash, role, active, created_at, updated_at)
                VALUES
                    (1, 'Ada', 'hash', 'admin', 1, :now, :now)
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees
                    (id, roaster, name, archived, created_by_id, created_at, updated_at)
                VALUES
                    (:id, 'Orbit', :name, 0, 1, :now, :now)
                """
            ),
            [{"id": index, "name": f"Lot {index}", "now": now} for index in range(1, 11)],
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        colors = list(
            connection.execute(text("SELECT chart_color FROM coffees ORDER BY id")).scalars()
        )
        nullable = next(
            column["nullable"]
            for column in inspect(connection).get_columns("coffees")
            if column["name"] == "chart_color"
        )
    engine.dispose()
    assert colors == [
        "#0072B2",
        "#D55E00",
        "#009E73",
        "#CC79A7",
        "#A6761D",
        "#6A3D9A",
        "#B2182B",
        "#4D4D4D",
        "#0072B2",
        "#D55E00",
    ]
    assert nullable is False

    command.downgrade(config, "5b0f2ea51d47")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        column_names = {column["name"] for column in inspect(connection).get_columns("coffees")}
    engine.dispose()
    assert "chart_color" not in column_names
