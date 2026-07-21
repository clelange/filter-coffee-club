from __future__ import annotations

import io
import logging
import os
import secrets
import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import Settings

logger = logging.getLogger(__name__)

register_heif_opener()

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}
SUPPORTED_FORMATS_LABEL = "JPEG, PNG, WebP, HEIC, or HEIF"


class CatalogPhotoOwner(Protocol):
    photo_path: str | None


def _normalized_webp(content: bytes, settings: Settings) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in SUPPORTED_FORMATS:
                raise HTTPException(
                    status_code=415, detail=f"Photo must be {SUPPORTED_FORMATS_LABEL}"
                )
            if getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) != 1:
                raise HTTPException(status_code=415, detail="Animated photos are not supported")
            if source.width * source.height > settings.max_catalog_photo_pixels:
                raise HTTPException(status_code=413, detail="Photo resolution is too large")

            source.load()
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (settings.catalog_photo_max_dimension, settings.catalog_photo_max_dimension),
                Image.Resampling.LANCZOS,
            )
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            output = io.BytesIO()
            image.save(
                output,
                format="WEBP",
                quality=settings.catalog_photo_webp_quality,
                method=6,
            )
            return output.getvalue()
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="Photo is not a valid supported image") from exc


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".photo-", dir=path.parent)
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


def _catalog_file(settings: Settings, public_path: str | None) -> Path | None:
    prefix = "/uploads/catalog/"
    if not public_path or not public_path.startswith(prefix):
        return None
    relative = public_path.removeprefix(prefix)
    root = settings.catalog_upload_dir.resolve()
    candidate = (root / relative).resolve()
    if candidate.parent != root:
        return None
    return candidate


def _remove_file(settings: Settings, public_path: str | None) -> None:
    path = _catalog_file(settings, public_path)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove replaced catalog photo", extra={"path": str(path)})


async def save_catalog_photo(
    upload: UploadFile,
    settings: Settings,
    db: Session,
    item: CatalogPhotoOwner,
) -> None:
    content = await upload.read(settings.max_catalog_photo_bytes + 1)
    if len(content) > settings.max_catalog_photo_bytes:
        bytes_per_mb = 1024 * 1024
        limit = settings.max_catalog_photo_bytes
        limit_label = (
            f"{limit // bytes_per_mb} MB" if limit % bytes_per_mb == 0 else f"{limit} bytes"
        )
        raise HTTPException(status_code=413, detail=f"Photo exceeds {limit_label}")
    normalized = await run_in_threadpool(_normalized_webp, content, settings)
    filename = f"photo-{secrets.token_hex(16)}.webp"
    destination = settings.catalog_upload_dir / filename
    await run_in_threadpool(_atomic_write, destination, normalized)

    old_path = item.photo_path
    item.photo_path = f"/uploads/catalog/{filename}"
    try:
        db.commit()
        db.refresh(item)
    except BaseException:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    _remove_file(settings, old_path)


def remove_catalog_photo(settings: Settings, db: Session, item: CatalogPhotoOwner) -> None:
    old_path = item.photo_path
    item.photo_path = None
    db.commit()
    db.refresh(item)
    _remove_file(settings, old_path)
