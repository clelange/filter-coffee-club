from __future__ import annotations

import pytest
from app.schemas import BrewCorrection, BrewInput, BrewUpdate
from pydantic import ValidationError


def brew_payload(**overrides: object) -> dict[str, object]:
    return {
        "coffee_id": 1,
        "grinder_id": 1,
        "dose_g": 15,
        "water_g": 240,
        "temperature_c": 94,
        "grinder_setting": 30,
        **overrides,
    }


@pytest.mark.parametrize("bloom_water_g", [None, 0, 240])
def test_brew_input_accepts_bloom_water_up_to_total_water(
    bloom_water_g: float | None,
) -> None:
    assert BrewInput(**brew_payload(bloom_water_g=bloom_water_g)).bloom_water_g == bloom_water_g


@pytest.mark.parametrize(
    ("schema", "extra"),
    [
        (BrewInput, {}),
        (BrewUpdate, {"revision": 1}),
        (BrewCorrection, {"total_brew_time_s": 180}),
    ],
)
def test_all_recipe_mutations_reject_bloom_water_above_total(
    schema: type[BrewInput], extra: dict[str, object]
) -> None:
    with pytest.raises(ValidationError, match="Bloom water must not exceed total water"):
        schema(**brew_payload(bloom_water_g=241, **extra))


def test_missing_target_ratio_defaults_to_the_current_actual_ratio() -> None:
    payload = BrewInput(**brew_payload())
    assert payload.target_ratio == 16


def test_explicit_target_ratio_is_preserved_separately_from_actual_amounts() -> None:
    payload = BrewInput(**brew_payload(dose_g=7.4, water_g=120, target_ratio=16.3))
    assert payload.target_ratio == 16.3
    assert payload.water_g / payload.dose_g != payload.target_ratio
