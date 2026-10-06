from __future__ import annotations

import io
import logging
import secrets
from pathlib import Path
from typing import Literal

from anyio import to_thread
from PIL import Image, UnidentifiedImageError
from sqlalchemy import update
from sqlalchemy.orm import Session

from .config import Settings
from .models import AppSettings
from .upload_storage import atomic_write as _atomic_write
from .upload_storage import upload_limit_label

logger = logging.getLogger(__name__)

LogoAttribute = Literal["logo_path", "brewing_logo_path"]
_ALLOWED_LOGOS = {
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
_UPLOAD_PREFIX = "/uploads/"
_OWNED_FILENAME_PREFIXES = ("logo-", "brewing-logo-")


class BrandingError(Exception):
    """A branding image cannot be stored."""


class UnsupportedLogoError(BrandingError):
    """The content or declared media type is not a supported logo."""


class LogoTooLargeError(BrandingError):
    """The logo exceeds the configured byte or pixel limit."""


def _inspect_logo(content: bytes, expected_format: str) -> tuple[bool, int]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            actual_format = image.format
            pixels = image.width * image.height
            image.verify()
    except (
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ):
        return False, 0
    return actual_format == expected_format, pixels


def _uploaded_logo_file(settings: Settings, public_path: str | None) -> Path | None:
    if not public_path or not public_path.startswith(_UPLOAD_PREFIX):
        return None
    relative = public_path.removeprefix(_UPLOAD_PREFIX)
    relative_path = Path(relative)
    if relative_path.name != relative or not relative.startswith(_OWNED_FILENAME_PREFIXES):
        return None
    if relative_path.suffix.lower() not in {".png", ".webp"}:
        return None
    root = settings.upload_dir.resolve()
    candidate = (root / relative_path).resolve()
    if candidate.parent != root:
        return None
    return candidate


def _remove_uploaded_logo(settings: Settings, public_path: str | None) -> None:
    path = _uploaded_logo_file(settings, public_path)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove replaced branding logo", extra={"path": str(path)})


async def store_logo(
    content: bytes,
    content_type: str | None,
    settings: Settings,
    filename_prefix: Literal["logo", "brewing-logo"],
) -> str:
    """Validate raw logo bytes and return the stored image's public path."""
    logo_type = _ALLOWED_LOGOS.get(content_type or "")
    if logo_type is None:
        raise UnsupportedLogoError("Logo must be PNG or WebP")

    if len(content) > settings.max_logo_bytes:
        limit_label = upload_limit_label(settings.max_logo_bytes)
        raise LogoTooLargeError(f"Logo exceeds {limit_label}")

    expected_format, suffix = logo_type
    valid, pixels = await to_thread.run_sync(_inspect_logo, content, expected_format)
    if not valid:
        raise UnsupportedLogoError("Logo contents do not match its file type")
    if pixels > settings.max_logo_pixels:
        raise LogoTooLargeError("Logo dimensions are too large")

    filename = f"{filename_prefix}-{secrets.token_hex(8)}{suffix}"
    destination = settings.upload_dir / filename
    await to_thread.run_sync(_atomic_write, destination, content)
    return f"{_UPLOAD_PREFIX}{filename}"


async def save_logo(
    content: bytes,
    content_type: str | None,
    settings: Settings,
    db: Session,
    item: AppSettings,
    attribute: LogoAttribute,
) -> None:
    """Store and attach a logo, cleaning up the new upload if persistence fails."""
    filename_prefix = "logo" if attribute == "logo_path" else "brewing-logo"
    path = await store_logo(content, content_type, settings, filename_prefix)
    replace_logo_path(db, settings, item, attribute, path, created_upload=path)


def replace_logo_path(
    db: Session,
    settings: Settings,
    item: AppSettings,
    attribute: LogoAttribute,
    new_path: str | None,
    *,
    created_upload: str | None = None,
) -> None:
    """Commit a logo change and remove uploads no longer referenced by either slot."""
    try:
        # Serialize path changes before refreshing a row loaded ahead of an upload await.
        db.execute(
            update(AppSettings)
            .where(AppSettings.id == item.id)
            .values(id=AppSettings.id)
            .execution_options(synchronize_session=False, autoflush=False)
        )
        db.refresh(item)
        old_path = getattr(item, attribute)
        setattr(item, attribute, new_path)
        retained_paths = {item.logo_path, item.brewing_logo_path}
        db.commit()
    except BaseException:
        try:
            db.rollback()
        finally:
            _remove_uploaded_logo(settings, created_upload)
        raise

    if old_path not in retained_paths:
        _remove_uploaded_logo(settings, old_path)
