from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .brews import BrewResponse

CatalogKind = Literal["coffee", "grinder", "dripper", "filter"]


class CatalogUsageItem(BaseModel):
    kind: CatalogKind
    item_id: int
    completed_brew_count: int
    last_completed_at: datetime | None


class CatalogUsageResponse(BaseModel):
    items: list[CatalogUsageItem]


class CatalogBrewResult(BrewResponse):
    rating_count: int | None = None
    average_liking: float | None = None


class CatalogInsights(BaseModel):
    kind: CatalogKind
    item_id: int
    completed_brew_count: int
    last_completed_at: datetime | None
    average_ratio: float | None
    average_temperature_c: float | None
    average_total_brew_time_s: float | None
    average_overall_throughput_g_s: float | None
    observed_grinder_setting_min: float | None
    observed_grinder_setting_max: float | None
    ratings_visible: bool
    rating_count: int | None
    average_liking: float | None
    recent_brews: list[CatalogBrewResult]
