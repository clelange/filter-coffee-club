from __future__ import annotations

import io
import logging
import secrets
from pathlib import Path
from typing import Protocol

from anyio import to_thread
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy.orm import Session

from .config import Settings
from .upload_storage import atomic_write as _atomic_write
from .upload_storage import upload_limit_label

logger = logging.getLogger(__name__)

register_heif_opener()

MULTI_PICTURE_STILL_FORMATS = {"MPO"}


class CatalogPhotoError(Exception):
    """A catalog photo cannot be processed or updated."""


class UnsupportedPhotoError(CatalogPhotoError):
    """The content is not a supported still image."""


class PhotoTooLargeError(CatalogPhotoError):
    """The content exceeds the configured byte or pixel limit."""


class MissingPhotoError(CatalogPhotoError):
    """Framing cannot be updated without a photo."""


class CatalogPhotoOwner(Protocol):
    photo_path: str | None
    photo_focus_x: float | None
    photo_focus_y: float | None
    photo_zoom: float | None


def apply_catalog_photo_framing(
    item: CatalogPhotoOwner,
    framing: tuple[float, float, float] | None,
) -> None:
    if framing is None:
        item.photo_focus_x = None
        item.photo_focus_y = None
        item.photo_zoom = None
        return
    item.photo_focus_x, item.photo_focus_y, item.photo_zoom = framing


def _normalized_webp(content: bytes, settings: Settings) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as source:
            if getattr(source, "is_animated", False) and (
                source.format not in MULTI_PICTURE_STILL_FORMATS
            ):
                raise UnsupportedPhotoError("Animated photos are not supported")
            source.seek(0)
            if source.width * source.height > settings.max_catalog_photo_pixels:
                raise PhotoTooLargeError("Photo resolution is too large")

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
    except CatalogPhotoError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise UnsupportedPhotoError("Photo is not a valid supported image") from exc


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


def _commit_photo_change(db: Session) -> None:
    try:
        db.commit()
    except BaseException:
        db.rollback()
        raise


async def save_catalog_photo(
    content: bytes,
    settings: Settings,
    db: Session,
    item: CatalogPhotoOwner,
    framing: tuple[float, float, float] | None = None,
) -> None:
    if len(content) > settings.max_catalog_photo_bytes:
        limit_label = upload_limit_label(settings.max_catalog_photo_bytes)
        raise PhotoTooLargeError(f"Photo exceeds {limit_label}")
    normalized = await to_thread.run_sync(_normalized_webp, content, settings)
    filename = f"photo-{secrets.token_hex(16)}.webp"
    destination = settings.catalog_upload_dir / filename
    await to_thread.run_sync(_atomic_write, destination, normalized)

    old_path = item.photo_path
    item.photo_path = f"/uploads/catalog/{filename}"
    apply_catalog_photo_framing(item, framing)
    try:
        _commit_photo_change(db)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    # Once committed, the new file belongs to the row even if a subsequent read fails.
    _remove_file(settings, old_path)
    db.refresh(item)


def remove_catalog_photo(settings: Settings, db: Session, item: CatalogPhotoOwner) -> None:
    old_path = item.photo_path
    item.photo_path = None
    apply_catalog_photo_framing(item, None)
    _commit_photo_change(db)
    _remove_file(settings, old_path)
    db.refresh(item)


def update_catalog_photo_framing(
    db: Session,
    item: CatalogPhotoOwner,
    framing: tuple[float, float, float] | None,
) -> None:
    if item.photo_path is None:
        raise MissingPhotoError("Catalog item has no photo to frame")
    apply_catalog_photo_framing(item, framing)
    _commit_photo_change(db)
    db.refresh(item)
