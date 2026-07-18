from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfilePublic(ORMModel):
    id: int
    display_name: str
    role: str
    active: bool


class BootstrapInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    pin: str
    device_mode: Literal["kiosk", "personal"] = "personal"

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class LoginInput(BaseModel):
    profile_id: int
    pin: str
    device_mode: Literal["kiosk", "personal"]

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class PinChange(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class ProfileCreate(BootstrapInput):
    role: Literal["member", "admin"] = "member"


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Literal["member", "admin"] | None = None
    active: bool | None = None
    pin: str | None = None

    @field_validator("pin")
    @classmethod
    def validate_optional_pin(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 4 or not value.isdigit()):
            raise ValueError("PIN must contain exactly four digits")
        return value


class SessionResponse(BaseModel):
    profile: ProfilePublic
    csrf_token: str
    device_mode: str
    expires_at: datetime


class CoffeeInput(BaseModel):
    roaster: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    country: str | None = None
    region: str | None = None
    producer: str | None = None
    process: str | None = None
    roast_level: str | None = None
    roast_date: date | None = None
    opened_date: date | None = None
    variety: str | None = None
    package_notes: str | None = None


class CoffeeResponse(CoffeeInput, ORMModel):
    id: int
    archived: bool
    cloned_from_id: int | None
    created_at: datetime


class GrinderInput(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    setting_unit: str = Field(default="clicks", min_length=1, max_length=40)
    setting_step: float = Field(default=1, gt=0)
    soft_min: float | None = None
    soft_max: float | None = None
    guidance: str | None = None

    @model_validator(mode="after")
    def validate_soft_range(self) -> GrinderInput:
        if (
            self.soft_min is not None
            and self.soft_max is not None
            and self.soft_min > self.soft_max
        ):
            raise ValueError("Soft minimum must not exceed soft maximum")
        return self


class GrinderResponse(GrinderInput, ORMModel):
    id: int
    archived: bool


class EquipmentInput(BaseModel):
    manufacturer: str | None = None
    model: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class DripperResponse(EquipmentInput, ORMModel):
    id: int
    archived: bool


class FilterInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    notes: str | None = None


class FilterResponse(FilterInput, ORMModel):
    id: int
    archived: bool


class GrinderRangeResponse(ORMModel):
    grinder_id: int
    setting_min: float
    setting_max: float


class GrinderRangeInput(BaseModel):
    grinder_id: int
    setting_min: float
    setting_max: float


class PresetResponse(ORMModel):
    id: int
    name: str
    ratio: float
    temperature_min_c: float
    temperature_max_c: float
    active: bool
    sort_order: int
    grinder_ranges: list[GrinderRangeResponse]


class PresetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    ratio: float = Field(gt=1, le=30)
    temperature_min_c: float = Field(ge=50, le=100)
    temperature_max_c: float = Field(ge=50, le=100)
    active: bool = True
    sort_order: int = 0
    grinder_ranges: list[GrinderRangeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ranges(self) -> PresetUpdate:
        if self.temperature_min_c > self.temperature_max_c:
            raise ValueError("Minimum temperature must not exceed maximum temperature")
        grinder_ids: set[int] = set()
        for item in self.grinder_ranges:
            if item.setting_min > item.setting_max:
                raise ValueError("Grinder range minimum must not exceed maximum")
            if item.grinder_id in grinder_ids:
                raise ValueError("A preset may define only one range per grinder")
            grinder_ids.add(item.grinder_id)
        return self


class FlavorTagInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    active: bool = True
    sort_order: int = 0


class BrewInput(BaseModel):
    coffee_id: int
    grinder_id: int
    dripper_id: int | None = None
    filter_id: int | None = None
    source_preset_id: int | None = None
    dose_g: float = Field(gt=0, le=500)
    water_g: float = Field(gt=0, le=5000)
    temperature_c: float = Field(ge=50, le=100)
    grinder_setting: float = Field(ge=0, le=1000)
    servings: int = Field(default=1, ge=1, le=30)
    target_flow_g_s: float | None = Field(default=None, gt=0, le=50)
    bloom_water_g: float | None = Field(default=None, ge=0, le=1000)
    bloom_time_s: int | None = Field(default=None, ge=0, le=1200)
    pour_count: int | None = Field(default=None, ge=1, le=30)
    technique_note: str | None = Field(default=None, max_length=1000)


class BrewFinalize(BaseModel):
    water_g: float | None = Field(default=None, gt=0, le=5000)
    total_brew_time_s: int = Field(gt=0, le=3600)


class BrewCorrection(BrewInput):
    total_brew_time_s: int = Field(gt=0, le=3600)


class BrewResponse(BrewInput):
    id: int
    operator_id: int
    operator_name: str
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


class FlavorTagResponse(ORMModel):
    id: int
    name: str
    parent_id: int | None
    active: bool
    sort_order: int


class RatingInput(BaseModel):
    liking: int = Field(ge=1, le=9)
    acidity: int = Field(ge=0, le=5)
    bitterness: int = Field(ge=0, le=5)
    sweetness: int = Field(ge=0, le=5)
    body: int = Field(ge=0, le=5)
    flavor_tag_ids: list[int] = Field(default_factory=list, max_length=5)

    @field_validator("flavor_tag_ids")
    @classmethod
    def unique_tags(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Flavor tags must be unique")
        return value


class RatingItem(RatingInput):
    profile_id: int
    profile_name: str
    updated_at: datetime


class RatingSummary(BaseModel):
    can_view: bool
    own_rating: RatingItem | None
    ratings: list[RatingItem] = Field(default_factory=list)
    count: int = 0
    averages: dict[str, float] = Field(default_factory=dict)
    flavor_counts: dict[str, int] = Field(default_factory=dict)


class RatingLinkResponse(BaseModel):
    active: bool
    brew: BrewResponse | None


class AppSettingsResponse(ORMModel):
    app_name: str
    subtitle: str
    public_base_url: str | None
    logo_path: str | None
    color_cream: str
    color_surface: str
    color_ink: str
    color_coffee: str
    color_cyan: str
    color_amber: str
    public_url_needs_configuration: bool = False


class AppSettingsUpdate(BaseModel):
    app_name: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(max_length=240)
    public_base_url: str | None = Field(default=None, max_length=500)
    color_cream: str
    color_surface: str
    color_ink: str
    color_coffee: str
    color_cyan: str
    color_amber: str

    @field_validator(
        "color_cream", "color_surface", "color_ink", "color_coffee", "color_cyan", "color_amber"
    )
    @classmethod
    def validate_color(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("Colors must be six-digit hexadecimal values")
        try:
            int(value[1:], 16)
        except ValueError as exc:
            raise ValueError("Colors must be six-digit hexadecimal values") from exc
        return value.upper()
