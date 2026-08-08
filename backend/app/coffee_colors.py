from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

COFFEE_COLOR_PALETTE = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#A6761D",
    "#6A3D9A",
    "#B2182B",
    "#4D4D4D",
)


def next_coffee_color(colors: Iterable[str], excluded: Iterable[str] = ()) -> str:
    counts = Counter(color.upper() for color in colors)
    excluded_colors = {color.upper() for color in excluded}
    candidates = [color for color in COFFEE_COLOR_PALETTE if color not in excluded_colors]
    return min(candidates or COFFEE_COLOR_PALETTE, key=lambda color: counts[color])
