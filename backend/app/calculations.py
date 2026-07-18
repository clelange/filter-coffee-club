from __future__ import annotations


def brew_ratio(water_g: float, dose_g: float) -> float:
    if dose_g <= 0:
        raise ValueError("Coffee dose must be positive")
    return round(water_g / dose_g, 2)


def serving_shortcut_from_water(servings: int, ratio: float) -> tuple[float, float]:
    if servings < 1 or ratio <= 0:
        raise ValueError("Servings and ratio must be positive")
    water_g = float(servings * 120)
    return round(water_g / ratio, 1), water_g


def serving_shortcut_from_coffee(servings: int, ratio: float) -> tuple[float, float]:
    if servings < 1 or ratio <= 0:
        raise ValueError("Servings and ratio must be positive")
    dose_g = float(servings * 8)
    return dose_g, round(dose_g * ratio)


def overall_throughput(water_g: float, total_brew_time_s: int | None) -> float | None:
    if not total_brew_time_s:
        return None
    return round(water_g / total_brew_time_s, 2)
