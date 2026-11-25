from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TapWater(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Literal["Tap water"]


Weight = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class MineralWater(BaseModel):
    """Weights of prepared concentrates and distilled water, stored per litre."""

    model_config = ConfigDict(extra="forbid")

    preset: Literal[
        "Melbourne",
        "WOC Budapest",
        "SCA",
        "Barista Hustle Water Recipe",
        "Rao Water",
        "Hendon Water",
        "Pretty Hard",
        "Hard dot AF",
    ]
    buffer_g: Weight
    magnesium_g: Weight
    distilled_g: Weight

    @model_validator(mode="after")
    def normalise_to_one_litre(self) -> MineralWater:
        weights = [Fraction(str(w)) for w in (self.buffer_g, self.magnesium_g, self.distilled_g)]
        total = sum(weights)
        if not total:
            raise ValueError("Enter a positive weight for at least one water ingredient")
        # Keep microgram precision. Assign rounding residue to the largest
        # remainders so reloading and resaving an adjusted mix is idempotent.
        portions = [weight * 1_000_000_000 / total for weight in weights]
        micrograms = [int(portion) for portion in portions]
        order = sorted(range(3), key=lambda i: portions[i] - micrograms[i], reverse=True)
        for i in order[: 1_000_000_000 - sum(micrograms)]:
            micrograms[i] += 1
        self.buffer_g, self.magnesium_g, self.distilled_g = (n / 1_000_000 for n in micrograms)
        return self


WaterProfile = Annotated[TapWater | MineralWater, Field(discriminator="preset")]
