from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..grinders import (
    GRINDER_DEFINITIONS,
    grinder_definition,
    translate_reference_setting,
    uses_integer_clicks,
)
from ..models import Grinder, RecipePreset
from ..schemas import GrinderDefinitionResponse, GrinderRangeResponse, PresetResponse, PresetUpdate


def validate_preset_grinder_ranges(db: Session, payload: PresetUpdate) -> None:
    for grinder_range in payload.custom_grinder_ranges:
        grinder = db.get(Grinder, grinder_range.grinder_id)
        if grinder is None:
            raise HTTPException(status_code=422, detail="Grinder not found")
        if grinder.definition_key != "custom":
            raise HTTPException(
                status_code=422,
                detail="Predefined grinder ranges are derived from the Comandante C40 reference",
            )
        if grinder.archived:
            raise HTTPException(status_code=422, detail="Archived grinders cannot receive ranges")
        if uses_integer_clicks(grinder.setting_unit) and not (
            float(grinder_range.setting_min).is_integer()
            and float(grinder_range.setting_max).is_integer()
        ):
            raise HTTPException(
                status_code=422,
                detail="Preset click ranges must use whole numbers",
            )


def preset_payload(preset: RecipePreset, grinders: list[Grinder]) -> PresetResponse:
    manual_ranges = {item.grinder_id: item for item in preset.grinder_ranges}
    effective_ranges: list[GrinderRangeResponse] = []
    for grinder in grinders:
        definition = grinder_definition(grinder.definition_key)
        if definition.reference_multiplier is not None:
            if preset.reference_setting_min is None or preset.reference_setting_max is None:
                continue
            setting_min = translate_reference_setting(
                preset.reference_setting_min, grinder.definition_key
            )
            setting_max = translate_reference_setting(
                preset.reference_setting_max, grinder.definition_key
            )
            assert setting_min is not None and setting_max is not None
            effective_ranges.append(
                GrinderRangeResponse(
                    grinder_id=grinder.id,
                    setting_min=setting_min,
                    setting_max=setting_max,
                    source=(
                        "reference" if grinder.definition_key == "comandante_c40" else "derived"
                    ),
                )
            )
            continue
        manual = manual_ranges.get(grinder.id)
        if manual is not None:
            effective_ranges.append(
                GrinderRangeResponse(
                    grinder_id=grinder.id,
                    setting_min=manual.setting_min,
                    setting_max=manual.setting_max,
                    source="custom",
                )
            )
    reference_range = (
        {
            "setting_min": preset.reference_setting_min,
            "setting_max": preset.reference_setting_max,
        }
        if preset.reference_setting_min is not None and preset.reference_setting_max is not None
        else None
    )
    return PresetResponse(
        id=preset.id,
        name=preset.name,
        ratio=preset.ratio,
        temperature_min_c=preset.temperature_min_c,
        temperature_max_c=preset.temperature_max_c,
        active=preset.active,
        sort_order=preset.sort_order,
        reference_grinder_range=reference_range,
        grinder_ranges=effective_ranges,
    )


def active_grinders(db: Session) -> list[Grinder]:
    return list(db.scalars(select(Grinder).where(Grinder.archived.is_(False))))


def grinder_definition_payloads() -> list[GrinderDefinitionResponse]:
    return [GrinderDefinitionResponse(**item.__dict__) for item in GRINDER_DEFINITIONS]
