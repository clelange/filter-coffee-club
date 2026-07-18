from __future__ import annotations

import pytest
from app.calculations import (
    brew_ratio,
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
