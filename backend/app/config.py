from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FCC_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str | None = None
    public_base_url: str = "http://filter-coffee-club.local"
    session_cookie: str = "fcc_session"
    cookie_secure: bool = False
    allowed_origins: str = ""
    timezone: str = "Europe/Zurich"
    frontend_dir: Path = Path("frontend/build")
    personal_session_hours: int = 84
    kiosk_session_hours: int = 4
    max_logo_bytes: int = 2 * 1024 * 1024
    max_catalog_photo_bytes: int = 12 * 1024 * 1024
    max_catalog_photo_pixels: int = 50_000_000
    catalog_photo_max_dimension: int = 1600
    catalog_photo_webp_quality: int = 82
    app_name: str = "Filter Coffee Club"
    log_level: str = Field(default="info")
    demo_mode: bool = False

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'fcc.sqlite3').resolve()}"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def catalog_upload_dir(self) -> Path:
        return self.upload_dir / "catalog"

    def prepare_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_upload_dir.mkdir(parents=True, exist_ok=True)
