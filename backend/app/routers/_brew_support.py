from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.orm import Session, selectinload

from ..calculations import (
    NORMAL_BREW_RATIO_MAX,
    NORMAL_BREW_RATIO_MIN,
    brew_ratio,
    brew_ratio_is_unusual,
    overall_throughput,
)
from ..models import AppSettings, Brew, Coffee, LoginSession, Profile, Rating, brew_operators
from ..schemas import BrewActivityItem, BrewInput, BrewResponse, ProfileIdentity
from ._common import conflict_detail, get_settings

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


def replay_idempotent_brew_creation(
    db: Session, brew: Brew, request_fingerprint: str
) -> BrewResponse:
    if brew.creation_request_hash == request_fingerprint:
        return brew_payload(load_brew(db, brew.id), include_token=True)
    raise HTTPException(
        status_code=409,
        detail="Idempotency key was already used for a different brew creation request",
    )


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
    raise HTTPException(
        status_code=422,
        detail=(
            f"Brew ratio 1:{ratio:g} is outside the normal "
            f"1:{NORMAL_BREW_RATIO_MIN:g}–1:{NORMAL_BREW_RATIO_MAX:g} range. "
            "Check that coffee dose and water are total batch amounts, or retry with "
            "X-Confirm-Unusual-Ratio: true."
        ),
    )


def validate_bloom_water(bloom_water_g: float | None, water_g: float) -> None:
    if bloom_water_g is not None and bloom_water_g > water_g:
        raise HTTPException(
            status_code=422,
            detail="Bloom water must not exceed total water",
        )


def reserve_available_coffee(db: Session, coffee_id: int) -> Coffee:
    """Keep a coffee available until the surrounding brew transaction commits."""

    # The no-op update acquires SQLite's writer lock without changing lifecycle data.
    reserved_id = db.scalar(
        text(
            """
            UPDATE coffees
            SET finished_at = finished_at
            WHERE id = :coffee_id
              AND archived IS FALSE
              AND finished_at IS NULL
            RETURNING id
            """
        ),
        {"coffee_id": coffee_id},
    )
    if reserved_id is not None:
        coffee = db.get(Coffee, reserved_id)
        assert coffee is not None
        return coffee

    db.rollback()
    if db.get(Coffee, coffee_id) is None:
        raise HTTPException(status_code=422, detail="Coffee not found")
    raise HTTPException(
        status_code=409,
        detail=conflict_detail("coffee_unavailable", "Coffee is no longer available for brewing"),
    )


def brew_payload(brew: Brew, include_token: bool = False) -> BrewResponse:
    ratio = brew_ratio(brew.water_g, brew.dose_g)
    throughput = overall_throughput(brew.water_g, brew.total_brew_time_s)
    return BrewResponse(
        id=brew.id,
        coffee_id=brew.coffee_id,
        operator_id=brew.operator_id,
        operators=[
            ProfileIdentity.model_validate(operator)
            for operator in sorted(
                brew.operators,
                key=lambda operator: (
                    operator.id != brew.operator_id,
                    operator.display_name.casefold(),
                ),
            )
        ],
        revision=brew.revision,
        grinder_id=brew.grinder_id,
        dripper_id=brew.dripper_id,
        filter_id=brew.filter_id,
        source_preset_id=brew.source_preset_id,
        cloned_from_id=brew.cloned_from_id,
        dose_g=brew.dose_g,
        water_g=brew.water_g,
        target_ratio=brew.target_ratio,
        temperature_c=brew.temperature_c,
        grinder_setting=brew.grinder_setting,
        servings=brew.servings,
        target_flow_g_s=brew.target_flow_g_s,
        bloom_water_g=brew.bloom_water_g,
        bloom_time_s=brew.bloom_time_s,
        pour_count=brew.pour_count,
        technique_note=brew.technique_note,
        total_brew_time_s=brew.total_brew_time_s,
        status=brew.status,
        completed_at=brew.completed_at,
        created_at=brew.created_at,
        ratio=ratio,
        overall_throughput_g_s=throughput,
        coffee_name=brew.coffee.name,
        coffee_roaster=brew.coffee.roaster,
        operator_name=brew.operator.display_name,
        grinder_name=f"{brew.grinder.manufacturer} {brew.grinder.model}",
        grinder_unit=brew.grinder.setting_unit,
        dripper_name=(
            " ".join(filter(None, [brew.dripper.manufacturer, brew.dripper.model]))
            if brew.dripper
            else None
        ),
        filter_name=brew.brew_filter.name if brew.brew_filter else None,
        rating_token=brew.rating_token if include_token else None,
    )


def brew_activity_payload(brew: Brew, include_token: bool = False) -> BrewActivityItem:
    return BrewActivityItem(
        id=brew.id,
        coffee_name=brew.coffee.name,
        coffee_roaster=brew.coffee.roaster,
        operators=[
            ProfileIdentity.model_validate(operator)
            for operator in sorted(
                brew.operators,
                key=lambda operator: (
                    operator.id != brew.operator_id,
                    operator.display_name.casefold(),
                ),
            )
        ],
        status=brew.status,
        rating_token=brew.rating_token if include_token else None,
    )


def load_brew(db: Session, brew_id: int) -> Brew:
    brew = db.scalar(
        select(Brew)
        .options(
            selectinload(Brew.coffee),
            selectinload(Brew.operator),
            selectinload(Brew.operators),
            selectinload(Brew.grinder),
            selectinload(Brew.dripper),
            selectinload(Brew.brew_filter),
            selectinload(Brew.ratings).selectinload(Rating.profile),
            selectinload(Brew.ratings).selectinload(Rating.flavor_tags),
        )
        .where(Brew.id == brew_id)
        .execution_options(populate_existing=True)
    )
    if brew is None:
        raise HTTPException(status_code=404, detail="Brew not found")
    return brew


def load_active_operator(db: Session, operator_id: int) -> Profile:
    operator = db.get(Profile, operator_id)
    if operator is None:
        raise HTTPException(status_code=404, detail="Operator not found")
    if not operator.active:
        raise HTTPException(status_code=422, detail="Operator must be active")
    return operator


def is_brew_operator(brew: Brew, profile_id: int) -> bool:
    return any(operator.id == profile_id for operator in brew.operators)


def selected_brewers(
    db: Session, operator_ids: list[int], primary_id: int, existing: list[Profile]
) -> list[Profile]:
    if primary_id not in operator_ids:
        raise HTTPException(status_code=422, detail="The primary brewer must remain selected")
    retained = {profile.id: profile for profile in existing}
    return [
        retained.get(profile_id) or load_active_operator(db, profile_id)
        for profile_id in operator_ids
    ]


def changed_brewers(
    db: Session,
    brew: Brew,
    operator_ids: list[int] | None,
    login_session: LoginSession,
    primary_id: int | None = None,
) -> list[Profile] | None:
    if operator_ids is None:
        return None
    if brew.operator_id != login_session.profile_id and login_session.profile.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only the primary brewer or an administrator may change brewers"
        )
    return selected_brewers(db, operator_ids, primary_id or brew.operator_id, brew.operators)


def reserve_active_brew_capacity(db: Session) -> None:
    get_settings(db)
    reserved = db.scalar(
        update(AppSettings)
        .where(
            AppSettings.id == 1,
            AppSettings.active_brew_count < AppSettings.max_active_brews,
        )
        .values(active_brew_count=AppSettings.active_brew_count + 1)
        .returning(AppSettings.id)
        .execution_options(synchronize_session=False)
    )
    if reserved is None:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=conflict_detail(
                "brew_capacity_reached",
                "The maximum number of parallel brews is already active",
            ),
        )


def release_active_brew_capacity(db: Session) -> None:
    released = db.scalar(
        update(AppSettings)
        .where(AppSettings.id == 1, AppSettings.active_brew_count > 0)
        .values(active_brew_count=AppSettings.active_brew_count - 1)
        .returning(AppSettings.id)
        .execution_options(synchronize_session=False)
    )
    if released is None:
        raise RuntimeError("Active brew capacity counter is inconsistent")


def commit_guarded_brew_update(
    db: Session,
    brew_id: int,
    expected_status: str,
    login_session: LoginSession,
    values: dict[str, object],
    status_detail: str,
    permission_detail: str,
    expected_revision: int | None = None,
    allow_collaborators: bool = False,
    release_capacity: bool = False,
    before_commit: Callable[[Session, int], None] | None = None,
    operators: list[Profile] | None = None,
) -> BrewResponse:
    conditions = [Brew.id == brew_id, Brew.status == expected_status]
    allow_collaborators = allow_collaborators and operators is None
    if expected_revision is not None:
        conditions.append(Brew.revision == expected_revision)
    if login_session.profile.role != "admin":
        if allow_collaborators:
            conditions.append(
                Brew.id.in_(
                    select(brew_operators.c.brew_id).where(
                        brew_operators.c.profile_id == login_session.profile_id
                    )
                )
            )
        else:
            conditions.append(Brew.operator_id == login_session.profile_id)
    guarded_values = {**values, "revision": Brew.revision + 1}
    updated_id = db.scalar(
        update(Brew)
        .where(*conditions)
        .values(**guarded_values)
        .returning(Brew.id)
        .execution_options(synchronize_session=False)
    )
    if updated_id is None:
        db.rollback()
        current = load_brew(db, brew_id)
        if current.status != expected_status:
            raise HTTPException(status_code=409, detail=status_detail)
        if login_session.profile.role != "admin" and (
            current.operator_id != login_session.profile_id
            if not allow_collaborators
            else not is_brew_operator(current, login_session.profile_id)
        ):
            raise HTTPException(status_code=403, detail=permission_detail)
        if expected_revision is not None and current.revision != expected_revision:
            raise HTTPException(status_code=409, detail="Brew changed; refresh and try again")
        raise HTTPException(status_code=409, detail="Brew changed; refresh and try again")
    if release_capacity:
        release_active_brew_capacity(db)
    if operators is not None:
        db.execute(delete(brew_operators).where(brew_operators.c.brew_id == brew_id))
        db.execute(
            insert(brew_operators),
            [{"brew_id": brew_id, "profile_id": operator.id} for operator in operators],
        )
    if before_commit is not None:
        db.flush()
        before_commit(db, updated_id)
    db.commit()
    return brew_payload(load_brew(db, updated_id), include_token=True)
