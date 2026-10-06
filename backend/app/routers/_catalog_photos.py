from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, Request

from ..catalog_photos import MissingPhotoError, PhotoTooLargeError, UnsupportedPhotoError
from ..schemas.photos import PhotoFraming


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


def ensure_catalog_photo_writes_allowed(request: Request) -> None:
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="Photo changes are disabled in demo mode")


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
