from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .profiles import ProfileIdentity


class BrewInput(BaseModel):
    coffee_id: int
    grinder_id: int
    dripper_id: int | None = None
    filter_id: int | None = None
    source_preset_id: int | None = None
    dose_g: float = Field(gt=0, le=500)
    water_g: float = Field(gt=0, le=5000)
    target_ratio: float | None = Field(default=None, gt=0, le=5000)
    temperature_c: float = Field(ge=50, le=100)
    grinder_setting: float = Field(ge=0, le=1000)
    servings: int = Field(default=1, ge=1, le=30)
    target_flow_g_s: float | None = Field(default=None, gt=0, le=50)
    bloom_water_g: float | None = Field(default=None, ge=0, le=1000)
    bloom_time_s: int | None = Field(default=None, ge=0, le=1200)
    pour_count: int | None = Field(default=None, ge=1, le=30)
    technique_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_bloom_water(self) -> BrewInput:
        if self.bloom_water_g is not None and self.bloom_water_g > self.water_g:
            raise ValueError("Bloom water must not exceed total water")
        if self.target_ratio is None:
            self.target_ratio = self.water_g / self.dose_g
        return self


class BrewParticipants(BaseModel):
    operator_ids: list[int] | None = Field(default=None, min_length=1)

    @field_validator("operator_ids")
    @classmethod
    def validate_operator_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None:
            if len(value) != len(set(value)) or any(item <= 0 for item in value):
                raise ValueError("Brewers must be distinct valid profiles")
            return sorted(value)
        return value


class BrewCreate(BrewInput, BrewParticipants):
    pass


class BrewUpdate(BrewCreate):
    revision: int = Field(ge=1)


class BrewFinalize(BrewParticipants):
    water_g: float | None = Field(default=None, gt=0, le=5000)
    total_brew_time_s: int = Field(gt=0, le=3600)
    revision: int = Field(ge=1)
    mark_coffee_finished: bool = False


class BrewOperatorUpdate(BaseModel):
    operator_id: int
    revision: int = Field(ge=1)


class BrewStatusChange(BaseModel):
    revision: int = Field(ge=1)


class BrewCorrection(BrewUpdate):
    operator_id: int | None = None
    total_brew_time_s: int = Field(gt=0, le=3600)


class BrewResponse(BrewInput):
    target_ratio: float
    id: int
    operator_id: int
    operator_name: str
    operators: list[ProfileIdentity]
    revision: int
    coffee_name: str
    coffee_roaster: str
    grinder_name: str
    grinder_unit: str
    dripper_name: str | None
    filter_name: str | None
    status: str
    ratio: float
    overall_throughput_g_s: float | None
    total_brew_time_s: int | None
    completed_at: datetime | None
    created_at: datetime
    cloned_from_id: int | None
    rating_token: str | None = None


class BrewActivityItem(BaseModel):
    id: int
    coffee_name: str
    coffee_roaster: str
    operators: list[ProfileIdentity]
    status: str
    rating_token: str | None = None


class ActiveBrewsResponse(BaseModel):
    brews: list[BrewActivityItem]
    recent_rating_brews: list[BrewActivityItem]
    active_count: int
    max_active_brews: int
    can_start: bool
