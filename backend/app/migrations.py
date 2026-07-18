from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import Settings


def run_migrations(settings: Settings) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(project_root / "alembic.ini")
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.resolved_database_url)
    config.attributes["settings"] = settings
    config.attributes["skip_logging_config"] = True
    command.upgrade(config, "head")
