from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypeVar

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..catalog_photos import (
    MissingPhotoError,
    PhotoTooLargeError,
    UnsupportedPhotoError,
    remove_catalog_photo,
    save_catalog_photo,
    update_catalog_photo_framing,
)
from ..models import BrewFilter, Coffee, Dripper, Grinder
from ..schemas.photos import PhotoFraming

PhotoItem = TypeVar("PhotoItem", Coffee, Grinder, Dripper, BrewFilter)


@contextmanager
def catalog_photo_http_errors() -> Iterator[None]:
    """Translate photo service failures at the HTTP boundary."""
    try:
        yield
    except PhotoTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedPhotoError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except MissingPhotoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _photo_item(request: Request, db: Session, model: type[PhotoItem], item_id: int) -> PhotoItem:
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="Photo changes are disabled in demo mode")
    item = db.get(model, item_id)
    if item is None:
        label = "Filter" if model is BrewFilter else model.__name__
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def photo_framing_tuple(framing: PhotoFraming | None) -> tuple[float, float, float] | None:
    if framing is None:
        return None
    return framing.focus_x, framing.focus_y, framing.zoom


def uploaded_photo_framing(
    focus_x: float | None,
    focus_y: float | None,
    zoom: float | None,
) -> tuple[float, float, float] | None:
    values = (focus_x, focus_y, zoom)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(
            status_code=422, detail="Photo framing fields must be provided together"
        )
    assert focus_x is not None and focus_y is not None and zoom is not None
    return focus_x, focus_y, zoom


async def upload_item_photo(
    request: Request,
    db: Session,
    model: type[PhotoItem],
    item_id: int,
    photo: UploadFile,
    focus_x: float | None,
    focus_y: float | None,
    zoom: float | None,
) -> PhotoItem:
    item = _photo_item(request, db, model, item_id)
    framing = uploaded_photo_framing(focus_x, focus_y, zoom)
    settings = request.app.state.settings
    content = await photo.read(settings.max_catalog_photo_bytes + 1)
    with catalog_photo_http_errors():
        await save_catalog_photo(content, settings, db, item, framing)
    return item


def reframe_item_photo(
    request: Request,
    db: Session,
    model: type[PhotoItem],
    item_id: int,
    framing: PhotoFraming | None,
) -> PhotoItem:
    item = _photo_item(request, db, model, item_id)
    with catalog_photo_http_errors():
        update_catalog_photo_framing(db, item, photo_framing_tuple(framing))
    return item


def delete_item_photo(
    request: Request, db: Session, model: type[PhotoItem], item_id: int
) -> PhotoItem:
    item = _photo_item(request, db, model, item_id)
    remove_catalog_photo(request.app.state.settings, db, item)
    return item
