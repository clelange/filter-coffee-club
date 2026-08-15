from __future__ import annotations

import pytest
from app.calculations import (
    brew_ratio,
    brew_ratio_is_unusual,
    overall_throughput,
    serving_shortcut_from_coffee,
    serving_shortcut_from_water,
)


def test_reference_sheet_serving_shortcuts_remain_ratio_aware() -> None:
    assert serving_shortcut_from_water(2, 16) == (15.0, 240.0)
    assert serving_shortcut_from_coffee(2, 16.5) == (16.0, 264)


def test_ratio_and_overall_throughput_labels_are_distinct() -> None:
    assert brew_ratio(242, 15) == 16.13
    assert overall_throughput(242, 180) == 1.34
    assert overall_throughput(242, None) is None
    with pytest.raises(ValueError):
        brew_ratio(240, 0)


@pytest.mark.parametrize(
    ("water_g", "dose_g", "unusual"),
    [
        (100, 10, False),
        (250, 10, False),
        (99, 10, True),
        (251, 10, True),
    ],
)
def test_unusual_brew_ratio_uses_inclusive_normal_boundaries(
    water_g: float, dose_g: float, unusual: bool
) -> None:
    assert brew_ratio_is_unusual(water_g, dose_g) is unusual
