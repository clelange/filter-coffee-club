from __future__ import annotations

import io
import logging
import os
import secrets
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .models import AppSettings

logger = logging.getLogger(__name__)

LogoAttribute = Literal["logo_path", "brewing_logo_path"]
_ALLOWED_LOGOS = {
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
_UPLOAD_PREFIX = "/uploads/"
_OWNED_FILENAME_PREFIXES = ("logo-", "brewing-logo-")


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


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".logo-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


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


async def store_logo_upload(
    logo: UploadFile, settings: Settings, filename_prefix: Literal["logo", "brewing-logo"]
) -> str:
    logo_type = _ALLOWED_LOGOS.get(logo.content_type or "")
    if logo_type is None:
        raise HTTPException(status_code=415, detail="Logo must be PNG or WebP")

    content = await logo.read(settings.max_logo_bytes + 1)
    if len(content) > settings.max_logo_bytes:
        bytes_per_mb = 1024 * 1024
        limit = settings.max_logo_bytes
        limit_label = (
            f"{limit // bytes_per_mb} MB" if limit % bytes_per_mb == 0 else f"{limit} bytes"
        )
        raise HTTPException(status_code=413, detail=f"Logo exceeds {limit_label}")

    expected_format, suffix = logo_type
    valid, pixels = await run_in_threadpool(_inspect_logo, content, expected_format)
    if not valid:
        raise HTTPException(status_code=415, detail="Logo contents do not match its file type")
    if pixels > settings.max_logo_pixels:
        raise HTTPException(status_code=413, detail="Logo dimensions are too large")

    filename = f"{filename_prefix}-{secrets.token_hex(8)}{suffix}"
    destination = settings.upload_dir / filename
    await run_in_threadpool(_atomic_write, destination, content)
    return f"{_UPLOAD_PREFIX}{filename}"


def replace_logo_path(
    db: Session,
    settings: Settings,
    item: AppSettings,
    attribute: LogoAttribute,
    new_path: str | None,
    *,
    created_upload: str | None = None,
) -> None:
    old_path = getattr(item, attribute)
    setattr(item, attribute, new_path)
    try:
        db.commit()
    except BaseException:
        db.rollback()
        _remove_uploaded_logo(settings, created_upload)
        raise

    retained_paths = {item.logo_path, item.brewing_logo_path}
    if old_path not in retained_paths:
        _remove_uploaded_logo(settings, old_path)
