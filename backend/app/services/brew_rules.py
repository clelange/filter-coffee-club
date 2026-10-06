from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.orm import Session

from ..calculations import (
    NORMAL_BREW_RATIO_MAX,
    NORMAL_BREW_RATIO_MIN,
    brew_ratio,
    brew_ratio_is_unusual,
)
from ..grinders import uses_integer_clicks
from ..models import Brew, Grinder, Profile
from ..schemas import BrewInput
from .brew_errors import BrewPermissionError, BrewValidationError, UnusualBrewRatioError
from .brew_store import load_active_operator
from .brew_types import BrewActor

brew_logger = logging.getLogger("fcc.brew")


def brew_creation_fingerprint(payload: BrewInput, profile_id: int) -> str:
    values = payload.model_dump(mode="json")
    operator_ids = values.pop("operator_ids", None)
    # Preserve fingerprints from before co-brewer selection was added. Omitting
    # the selection and explicitly selecting only the creator mean the same thing.
    if operator_ids is not None and operator_ids != [profile_id]:
        values["operator_ids"] = operator_ids
    canonical_request = json.dumps(
        {
            "payload": values,
            "profile_id": profile_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_request.encode()).hexdigest()


def log_unusual_brew_ratio(
    event: str,
    *,
    action: str,
    brew_id: int | None,
    dose_g: float,
    water_g: float,
    ratio: float,
) -> None:
    brew_logger.warning(
        event,
        extra={
            "fields": {
                "action": action,
                "brew_id": brew_id,
                "dose_g": dose_g,
                "water_g": water_g,
                "ratio": ratio,
            }
        },
    )


def validate_brew_ratio(
    water_g: float,
    dose_g: float,
    *,
    action: str,
    confirmed: bool,
    brew_id: int | None = None,
) -> float | None:
    ratio = brew_ratio(water_g, dose_g)
    if not brew_ratio_is_unusual(water_g, dose_g):
        return None
    raw_ratio = water_g / dose_g
    if NORMAL_BREW_RATIO_MIN <= ratio <= NORMAL_BREW_RATIO_MAX:
        ratio = round(raw_ratio, 5)
    if confirmed:
        return ratio
    log_unusual_brew_ratio(
        "unusual_brew_ratio_blocked",
        action=action,
        brew_id=brew_id,
        dose_g=dose_g,
        water_g=water_g,
        ratio=ratio,
    )
    raise UnusualBrewRatioError(ratio)


def validate_bloom_water(bloom_water_g: float | None, water_g: float) -> None:
    if bloom_water_g is not None and bloom_water_g > water_g:
        raise BrewValidationError("Bloom water must not exceed total water")


def selected_brewers(
    db: Session, operator_ids: list[int], primary_id: int, existing: list[Profile]
) -> list[Profile]:
    if primary_id not in operator_ids:
        raise BrewValidationError("The primary brewer must remain selected")
    retained = {profile.id: profile for profile in existing}
    return [
        retained.get(profile_id) or load_active_operator(db, profile_id)
        for profile_id in operator_ids
    ]


def changed_brewers(
    db: Session,
    brew: Brew,
    operator_ids: list[int] | None,
    actor: BrewActor,
    primary_id: int | None = None,
) -> list[Profile] | None:
    if operator_ids is None:
        return None
    if brew.operator_id != actor.profile_id and not actor.is_admin:
        raise BrewPermissionError("Only the primary brewer or an administrator may change brewers")
    return selected_brewers(db, operator_ids, primary_id or brew.operator_id, brew.operators)


def validate_grinder_setting(db: Session, grinder_id: int, setting: float) -> None:
    grinder = db.get(Grinder, grinder_id)
    if grinder is None:
        raise BrewValidationError("Grinder not found")
    if uses_integer_clicks(grinder.setting_unit) and not float(setting).is_integer():
        raise BrewValidationError("Grinder click settings must be whole numbers")
