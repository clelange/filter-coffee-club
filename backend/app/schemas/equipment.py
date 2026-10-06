from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ._base import ORMModel
from .photos import PhotoFraming

GrinderDefinitionKey = Literal["comandante_c40", "kingrinder_k6", "custom"]


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
        if self.setting_unit.strip().lower() in {"click", "clicks"}:
            click_values = (self.setting_step, self.soft_min, self.soft_max)
            if any(value is not None and not float(value).is_integer() for value in click_values):
                raise ValueError("Click-based grinder settings must use whole numbers")
        return self


class GrinderResponse(GrinderInput, ORMModel):
    id: int
    definition_key: GrinderDefinitionKey
    photo_path: str | None
    photo_framing: PhotoFraming | None
    archived: bool


class GrinderPresetRangeInput(BaseModel):
    preset_id: int
    setting_min: float | None = None
    setting_max: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> GrinderPresetRangeInput:
        if (self.setting_min is None) != (self.setting_max is None):
            raise ValueError("Custom preset ranges require both a minimum and maximum")
        if (
            self.setting_min is not None
            and self.setting_max is not None
            and self.setting_min > self.setting_max
        ):
            raise ValueError("Grinder range minimum must not exceed maximum")
        return self


class GrinderCreate(BaseModel):
    definition_key: GrinderDefinitionKey
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    setting_unit: str | None = Field(default=None, max_length=40)
    setting_step: float | None = Field(default=None, gt=0)
    soft_min: float | None = None
    soft_max: float | None = None
    guidance: str | None = None
    preset_ranges: list[GrinderPresetRangeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_custom_fields(self) -> GrinderCreate:
        if self.definition_key != "custom":
            custom_values = (
                self.manufacturer,
                self.model,
                self.setting_unit,
                self.setting_step,
                self.soft_min,
                self.soft_max,
                self.guidance,
            )
            if any(value is not None for value in custom_values) or self.preset_ranges:
                raise ValueError("Predefined grinders use canonical equipment details")
            return self
        required = {
            "manufacturer": self.manufacturer,
            "model": self.model,
            "setting_unit": self.setting_unit,
            "setting_step": self.setting_step,
        }
        if any(
            value is None or (isinstance(value, str) and not value.strip())
            for value in required.values()
        ):
            raise ValueError("Custom grinders require manufacturer, model, unit, and step")
        if (
            self.soft_min is not None
            and self.soft_max is not None
            and self.soft_min > self.soft_max
        ):
            raise ValueError("Soft minimum must not exceed soft maximum")
        if (self.setting_unit or "").strip().lower() in {"click", "clicks"}:
            click_values = (self.setting_step, self.soft_min, self.soft_max)
            if any(value is not None and not float(value).is_integer() for value in click_values):
                raise ValueError("Click-based grinder settings must use whole numbers")
            for item in self.preset_ranges:
                values = (item.setting_min, item.setting_max)
                if any(value is not None and not float(value).is_integer() for value in values):
                    raise ValueError("Click-based grinder settings must use whole numbers")
        preset_ids = [item.preset_id for item in self.preset_ranges]
        if len(preset_ids) != len(set(preset_ids)):
            raise ValueError("A custom grinder may define only one range per preset")
        return self


class GrinderDefinitionResponse(BaseModel):
    key: GrinderDefinitionKey
    label: str
    manufacturer: str | None
    model: str | None
    setting_unit: str
    setting_step: float
    soft_min: float | None
    soft_max: float | None
    guidance: str | None
    reference_multiplier: float | None
    clicks_per_rotation: int | None


class EquipmentInput(BaseModel):
    manufacturer: str | None = None
    model: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class DripperResponse(EquipmentInput, ORMModel):
    id: int
    photo_path: str | None
    photo_framing: PhotoFraming | None
    archived: bool


class FilterInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    notes: str | None = None


class FilterResponse(FilterInput, ORMModel):
    id: int
    photo_path: str | None
    photo_framing: PhotoFraming | None
    archived: bool
