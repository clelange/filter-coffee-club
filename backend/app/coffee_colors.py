from __future__ import annotations

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


def rgb(color: str) -> tuple[int, ...]:
    return tuple(int(color[offset : offset + 2], 16) for offset in (1, 3, 5))


def luminance(color: str) -> float:
    values = [channel / 255 for channel in rgb(color)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values
    ]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(first: str, second: str) -> float:
    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


def next_coffee_color(
    colors: Iterable[str], excluded: Iterable[str] = (), surface: str = "#FFFDFC"
) -> str:
    """Keep the familiar palette first, then choose spaced, unused RGB colours.

    The odd multiplier visits every 24-bit RGB value before repeating. The same
    deterministic algorithm is used by the frontend preview. Stored assignments
    are never recomputed when the catalog grows.
    """
    used = {color.upper() for color in (*colors, *excluded)}
    for color in COFFEE_COLOR_PALETTE:
        if color not in used and contrast_ratio(color, surface) >= 3:
            return color
    candidates = []
    for index in range(1 << 24):
        color = f"#{(index * 0x9E3779 + 0x4B6A80) & 0xFFFFFF:06X}"
        if color not in used and contrast_ratio(color, surface) >= 3:
            candidates.append(color)
            if len(candidates) == 64:
                break
    if not candidates:
        return "#000000" if luminance(surface) > 0.179 else "#FFFFFF"
    peers = [rgb(color) for color in used]
    return max(
        candidates,
        key=lambda color: min(
            (sum((a - b) ** 2 for a, b in zip(rgb(color), peer)) for peer in peers), default=0
        ),
    )
