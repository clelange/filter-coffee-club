from __future__ import annotations

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class GrinderDefinition:
    key: str
    label: str
    manufacturer: str | None
    model: str | None
    setting_unit: str
    setting_step: float
    soft_min: float | None
    soft_max: float | None
    guidance: str | None
    reference_multiplier: float | None
    clicks_per_rotation: int | None = None


GRINDER_DEFINITIONS: tuple[GrinderDefinition, ...] = (
    GrinderDefinition(
        key="comandante_c40",
        label="Comandante C40",
        manufacturer="Comandante",
        model="C40",
        setting_unit="clicks",
        setting_step=1,
        soft_min=0,
        soft_max=50,
        guidance=(
            "Count clicks outward from click zero. Values outside the range are "
            "allowed with a warning."
        ),
        reference_multiplier=1,
    ),
    GrinderDefinition(
        key="kingrinder_k6",
        label="KINGrinder K6",
        manufacturer="KINGrinder",
        model="K6",
        setting_unit="clicks",
        setting_step=1,
        soft_min=15,
        soft_max=150,
        guidance=(
            "Count total clicks outward from zero on the external dial. One full turn "
            "is 60 clicks; FCC presets are starting points converted from C40 clicks."
        ),
        reference_multiplier=3.2,
        clicks_per_rotation=60,
    ),
    GrinderDefinition(
        key="custom",
        label="Custom",
        manufacturer=None,
        model=None,
        setting_unit="clicks",
        setting_step=1,
        soft_min=0,
        soft_max=50,
        guidance=None,
        reference_multiplier=None,
    ),
)

GRINDER_DEFINITIONS_BY_KEY = {item.key: item for item in GRINDER_DEFINITIONS}


def grinder_definition(key: str) -> GrinderDefinition:
    return GRINDER_DEFINITIONS_BY_KEY.get(key, GRINDER_DEFINITIONS_BY_KEY["custom"])


def recognize_grinder_definition(manufacturer: str, model: str) -> str:
    normalized_manufacturer = manufacturer.strip().casefold()
    normalized_model = model.strip().casefold()
    if normalized_manufacturer == "comandante" and normalized_model in {
        "c40",
        "c40 mk3",
        "c40 mk4",
    }:
        return "comandante_c40"
    if normalized_manufacturer == "kingrinder" and normalized_model == "k6":
        return "kingrinder_k6"
    return "custom"


def round_to_step(value: float, step: float) -> float:
    snapped = floor(value / step + 0.5) * step
    return int(snapped) if float(snapped).is_integer() else snapped


def translate_reference_setting(value: float, definition_key: str) -> float | None:
    definition = grinder_definition(definition_key)
    if definition.reference_multiplier is None:
        return None
    return round_to_step(value * definition.reference_multiplier, definition.setting_step)
