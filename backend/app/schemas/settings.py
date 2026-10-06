from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ._base import ORMModel


class AppSettingsResponse(ORMModel):
    app_name: str
    app_version: str = "development"
    subtitle: str
    public_base_url: str | None
    logo_path: str | None
    brewing_logo_path: str | None
    color_cream: str
    color_surface: str
    color_ink: str
    color_coffee: str
    color_cyan: str
    color_amber: str
    max_active_brews: int
    public_url_needs_configuration: bool = False
    demo_mode: bool = False
    demo_notice: str | None = None
    demo_pin: str | None = None
    demo_profile_names: list[str] = Field(default_factory=list)


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
    max_active_brews: int = Field(ge=1, le=20)

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

    @model_validator(mode="after")
    def validate_palette_contrast(self) -> AppSettingsUpdate:
        checks = (
            ("Ink on the background", self.color_ink, self.color_cream),
            ("Ink on surfaces", self.color_ink, self.color_surface),
            ("Coffee buttons with white text", self.color_coffee, "#FFFFFF"),
            ("Links on the background", self.color_cyan, self.color_cream),
            ("Links on surfaces", self.color_cyan, self.color_surface),
            ("Accent notices with dark text", self.color_amber, "#21180B"),
        )
        failures = [
            f"{label} ({_contrast_ratio(foreground, background):.2f}:1)"
            for label, foreground, background in checks
            if _contrast_ratio(foreground, background) < 4.5
        ]
        if failures:
            raise ValueError(
                "Palette colors must provide at least 4.5:1 contrast: " + "; ".join(failures)
            )
        return self


def _contrast_ratio(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = []
        for offset in (1, 3, 5):
            value = int(color[offset : offset + 2], 16) / 255
            channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722

    first_luminance = luminance(first)
    second_luminance = luminance(second)
    light = max(first_luminance, second_luminance)
    dark = min(first_luminance, second_luminance)
    return (light + 0.05) / (dark + 0.05)
