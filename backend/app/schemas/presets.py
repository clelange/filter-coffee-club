from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ._base import ORMModel


class GrinderRangeResponse(ORMModel):
    grinder_id: int
    setting_min: float
    setting_max: float
    source: Literal["reference", "derived", "custom"]


class GrinderRangeInput(BaseModel):
    grinder_id: int
    setting_min: float
    setting_max: float


class ReferenceGrinderRangeInput(BaseModel):
    setting_min: float
    setting_max: float

    @model_validator(mode="after")
    def validate_range(self) -> ReferenceGrinderRangeInput:
        if self.setting_min > self.setting_max:
            raise ValueError("Grinder range minimum must not exceed maximum")
        if not (float(self.setting_min).is_integer() and float(self.setting_max).is_integer()):
            raise ValueError("Comandante C40 reference ranges must use whole clicks")
        return self


class PresetResponse(ORMModel):
    id: int
    name: str
    ratio: float
    temperature_min_c: float
    temperature_max_c: float
    active: bool
    sort_order: int
    reference_grinder_range: ReferenceGrinderRangeInput | None
    grinder_ranges: list[GrinderRangeResponse]


class PresetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    ratio: float = Field(gt=1, le=30)
    temperature_min_c: float = Field(ge=50, le=100)
    temperature_max_c: float = Field(ge=50, le=100)
    active: bool = True
    sort_order: int = 0
    reference_grinder_range: ReferenceGrinderRangeInput | None = None
    custom_grinder_ranges: list[GrinderRangeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ranges(self) -> PresetUpdate:
        if self.temperature_min_c > self.temperature_max_c:
            raise ValueError("Minimum temperature must not exceed maximum temperature")
        grinder_ids: set[int] = set()
        for item in self.custom_grinder_ranges:
            if item.setting_min > item.setting_max:
                raise ValueError("Grinder range minimum must not exceed maximum")
            if item.grinder_id in grinder_ids:
                raise ValueError("A preset may define only one range per grinder")
            grinder_ids.add(item.grinder_id)
        return self
