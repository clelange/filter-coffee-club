from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from ._base import ORMModel
from .photos import PhotoFraming


class CoffeeInput(BaseModel):
    roaster: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    country: str | None = None
    region: str | None = None
    producer: str | None = None
    purchase_location: str | None = Field(default=None, max_length=160)
    process: str | None = None
    roast_level: str | None = None
    roast_date: date | None = None
    opened_date: date | None = None
    variety: str | None = None
    package_notes: str | None = None
    chart_color: str | None = None

    @field_validator("chart_color")
    @classmethod
    def validate_chart_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if re.fullmatch(r"#[0-9A-F]{6}", normalized) is None:
            raise ValueError("Chart color must use #RRGGBB format")
        return normalized

    @field_validator("purchase_location", mode="before")
    @classmethod
    def normalize_purchase_location(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class CoffeeResponse(CoffeeInput, ORMModel):
    id: int
    chart_color: str
    photo_path: str | None
    photo_framing: PhotoFraming | None
    finished_at: datetime | None
    archived: bool
    available: bool
    cloned_from_id: int | None
    created_at: datetime
