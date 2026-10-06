from __future__ import annotations

from pydantic import BaseModel, Field


class PhotoFraming(BaseModel):
    focus_x: float = Field(ge=0, le=1)
    focus_y: float = Field(ge=0, le=1)
    zoom: float = Field(ge=1, le=3)


class PhotoFramingUpdate(BaseModel):
    photo_framing: PhotoFraming | None
