"""Brew commands commit recipe, membership, capacity and outbox changes together.

Callers supply authenticated actors and notification configuration. Transport checks,
demo policy and response serialization remain in the routers.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from functools import wraps

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import utcnow
from ..mattermost import cancel_brew_notifications, enqueue_brew_notification
from ..models import Brew, brew_operators
from ..schemas.brews import (
    BrewCorrection,
    BrewCreate,
    BrewFinalize,
    BrewOperatorUpdate,
    BrewStatusChange,
    BrewUpdate,
)
from .brew_errors import (
    BrewConflictError,
    BrewNotFoundError,
    BrewPermissionError,
)
from .brew_rules import (
    brew_creation_fingerprint,
    changed_brewers,
    log_unusual_brew_ratio,
    selected_brewers,
    validate_bloom_water,
    validate_brew_ratio,
    validate_grinder_setting,
)
from .brew_store import (
    commit_guarded_brew_update,
    is_brew_operator,
    load_active_operator,
    load_brew,
    replay_idempotent_brew_creation,
    reserve_active_brew_capacity,
    reserve_available_coffee,
)
from .brew_types import BrewActor, BrewNotifications


def _rollback_on_failure(workflow: Callable[..., Brew]) -> Callable[..., Brew]:
    @wraps(workflow)
    def run(db: Session, *args, **kwargs) -> Brew:
        try:
            return workflow(db, *args, **kwargs)
        except BaseException:
            db.rollback()
            raise

    return run


@_rollback_on_failure
def create_brew(
    db: Session,
    payload: BrewCreate,
    actor: BrewActor,
    notifications: BrewNotifications,
    *,
    idempotency_key: str | None = None,
    confirm_unusual_ratio: bool = False,
    before_create: Callable[[], None] | None = None,
) -> Brew:
    request_fingerprint = brew_creation_fingerprint(payload, actor.profile_id)
    if idempotency_key is not None:
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is not None:
            return replay_idempotent_brew_creation(db, existing, request_fingerprint)
    if before_create is not None:
        before_create()
    reserve_available_coffee(db, payload.coffee_id)
    validate_grinder_setting(db, payload.grinder_id, payload.grinder_setting)
    confirmed_ratio = validate_brew_ratio(
        payload.water_g,
        payload.dose_g,
        action="create",
        confirmed=confirm_unusual_ratio,
    )
    try:
        reserve_active_brew_capacity(db)
    except BrewConflictError:
        if idempotency_key is not None:
            existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
            if existing is not None:
                return replay_idempotent_brew_creation(db, existing, request_fingerprint)
        raise
    operators = selected_brewers(
        db,
        payload.operator_ids or [actor.profile_id],
        actor.profile_id,
        [load_active_operator(db, actor.profile_id)],
    )
    brew = Brew(
        **payload.model_dump(exclude={"operator_ids"}),
        operator_id=actor.profile_id,
        operators=operators,
        creation_token=idempotency_key,
        creation_request_hash=request_fingerprint if idempotency_key else None,
    )
    db.add(brew)
    try:
        enqueue_brew_notification(
            db,
            brew,
            "brew_started",
            notifications.public_base_url,
            demo_mode=notifications.demo_mode,
        )
        db.commit()
    except IntegrityError:
        if idempotency_key is None:
            raise
        db.rollback()
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is None:
            raise
        return replay_idempotent_brew_creation(db, existing, request_fingerprint)
    result = load_brew(db, brew.id)
    if confirmed_ratio is not None:
        log_unusual_brew_ratio(
            "unusual_brew_ratio_confirmed",
            action="create",
            brew_id=brew.id,
            dose_g=payload.dose_g,
            water_g=payload.water_g,
            ratio=confirmed_ratio,
        )
    return result


@_rollback_on_failure
def update_brew(
    db: Session,
    brew_id: int,
    payload: BrewUpdate,
    actor: BrewActor,
    *,
    confirm_unusual_ratio: bool = False,
) -> Brew:
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise BrewConflictError("Only draft brews can be edited")
    if not is_brew_operator(brew, actor.profile_id) and not actor.is_admin:
        raise BrewPermissionError("Only a brew operator may edit this draft")
    if payload.coffee_id != brew.coffee_id:
        reserve_available_coffee(db, payload.coffee_id)
    validate_grinder_setting(db, payload.grinder_id, payload.grinder_setting)
    confirmed_ratio = validate_brew_ratio(
        payload.water_g,
        payload.dose_g,
        action="update",
        confirmed=confirm_unusual_ratio,
        brew_id=brew.id,
    )
    result = commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        actor,
        payload.model_dump(exclude={"revision", "operator_ids"}),
        "Only draft brews can be edited",
        "Only a brew operator may edit this draft",
        expected_revision=payload.revision,
        allow_collaborators=True,
        operators=changed_brewers(db, brew, payload.operator_ids, actor),
    )
    if confirmed_ratio is not None:
        log_unusual_brew_ratio(
            "unusual_brew_ratio_confirmed",
            action="update",
            brew_id=brew.id,
            dose_g=payload.dose_g,
            water_g=payload.water_g,
            ratio=confirmed_ratio,
        )
    return result


@_rollback_on_failure
def join_brew(db: Session, brew_id: int, actor: BrewActor) -> Brew:
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise BrewConflictError("Only active brews can be joined")
    if is_brew_operator(brew, actor.profile_id):
        return brew
    joined_id = db.scalar(
        update(Brew)
        .where(
            Brew.id == brew.id,
            Brew.status == "draft",
            ~Brew.id.in_(
                select(brew_operators.c.brew_id).where(
                    brew_operators.c.profile_id == actor.profile_id
                )
            ),
        )
        .values(revision=Brew.revision + 1)
        .returning(Brew.id)
        .execution_options(synchronize_session=False)
    )
    if joined_id is None:
        db.rollback()
        current = load_brew(db, brew.id)
        if current.status != "draft":
            raise BrewConflictError("Only active brews can be joined")
        if is_brew_operator(current, actor.profile_id):
            return current
        raise BrewConflictError("Brew changed; refresh and try again")
    db.execute(
        insert(brew_operators).values(
            brew_id=brew.id,
            profile_id=actor.profile_id,
        )
    )
    db.commit()
    return load_brew(db, brew.id)


@_rollback_on_failure
def update_brew_operator(
    db: Session, brew_id: int, payload: BrewOperatorUpdate, actor: BrewActor
) -> Brew:
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise BrewConflictError("Only draft brews can change operator")
    if brew.operator_id != actor.profile_id and not actor.is_admin:
        raise BrewPermissionError("Only the operator or an administrator may reassign this brew")
    operator = load_active_operator(db, payload.operator_id)
    if not is_brew_operator(brew, operator.id):
        db.execute(insert(brew_operators).values(brew_id=brew.id, profile_id=operator.id))
    return commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        actor,
        {"operator_id": operator.id},
        "Only draft brews can change operator",
        "Only the operator or an administrator may reassign this brew",
        expected_revision=payload.revision,
    )


@_rollback_on_failure
def correct_completed_brew(
    db: Session,
    brew_id: int,
    payload: BrewCorrection,
    actor: BrewActor,
    *,
    confirm_unusual_ratio: bool = False,
) -> Brew:
    brew = load_brew(db, brew_id)
    if brew.status != "completed":
        raise BrewConflictError("Only completed brews need correction")
    if brew.operator_id != actor.profile_id and not actor.is_admin:
        raise BrewPermissionError("Only the operator or an administrator may correct this brew")
    validate_grinder_setting(db, payload.grinder_id, payload.grinder_setting)
    confirmed_ratio = validate_brew_ratio(
        payload.water_g,
        payload.dose_g,
        action="correct",
        confirmed=confirm_unusual_ratio,
        brew_id=brew.id,
    )
    values: dict[str, object] = payload.model_dump(
        exclude={"operator_id", "operator_ids", "revision"}
    )
    operators = changed_brewers(db, brew, payload.operator_ids, actor, payload.operator_id)
    if payload.operator_id is not None:
        operator = load_active_operator(db, payload.operator_id)
        values["operator_id"] = operator.id
        if operators is None:
            # Preserve the existing primary-transfer behavior for older clients.
            operators = list(brew.operators)
            if len(operators) == 1 and operators[0].id == brew.operator_id:
                operators = [operator]
            elif operator.id not in {item.id for item in operators}:
                operators.append(operator)
    result = commit_guarded_brew_update(
        db,
        brew.id,
        "completed",
        actor,
        values,
        "Only completed brews need correction",
        "Only the operator or an administrator may correct this brew",
        expected_revision=payload.revision,
        operators=operators,
    )
    if confirmed_ratio is not None:
        log_unusual_brew_ratio(
            "unusual_brew_ratio_confirmed",
            action="correct",
            brew_id=brew.id,
            dose_g=payload.dose_g,
            water_g=payload.water_g,
            ratio=confirmed_ratio,
        )
    return result


@_rollback_on_failure
def finalize_brew(
    db: Session,
    brew_id: int,
    payload: BrewFinalize,
    actor: BrewActor,
    notifications: BrewNotifications,
    *,
    confirm_unusual_ratio: bool = False,
) -> Brew:
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise BrewConflictError("Only draft brews can be finalized")
    if not is_brew_operator(brew, actor.profile_id) and not actor.is_admin:
        raise BrewPermissionError("Only a brew operator may finalize this brew")
    final_water_g = payload.water_g if payload.water_g is not None else brew.water_g
    validate_bloom_water(brew.bloom_water_g, final_water_g)
    confirmed_ratio = validate_brew_ratio(
        final_water_g,
        brew.dose_g,
        action="finalize",
        confirmed=confirm_unusual_ratio,
        brew_id=brew.id,
    )
    values: dict[str, object] = {
        "total_brew_time_s": payload.total_brew_time_s,
        "status": "completed",
        "completed_at": utcnow(),
        "rating_token": secrets.token_urlsafe(24),
    }
    if payload.water_g is not None:
        values["water_g"] = payload.water_g
    if (
        payload.mark_coffee_finished
        and not brew.coffee.archived
        and brew.coffee.finished_at is None
    ):
        brew.coffee.finished_at = utcnow()
    result = commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        actor,
        values,
        "Only draft brews can be finalized",
        "Only a brew operator may finalize this brew",
        expected_revision=payload.revision,
        allow_collaborators=True,
        operators=changed_brewers(db, brew, payload.operator_ids, actor),
        release_capacity=True,
        before_commit=lambda callback_db, updated_id: enqueue_brew_notification(
            callback_db,
            load_brew(callback_db, updated_id),
            "ready_to_rate",
            notifications.public_base_url,
            demo_mode=notifications.demo_mode,
        ),
    )
    if confirmed_ratio is not None:
        log_unusual_brew_ratio(
            "unusual_brew_ratio_confirmed",
            action="finalize",
            brew_id=brew.id,
            dose_g=brew.dose_g,
            water_g=final_water_g,
            ratio=confirmed_ratio,
        )
    return result


@_rollback_on_failure
def clone_brew(
    db: Session,
    brew_id: int,
    actor: BrewActor,
    notifications: BrewNotifications,
    *,
    idempotency_key: str | None = None,
    before_create: Callable[[], None] | None = None,
) -> Brew:
    fingerprint = hashlib.sha256(f"clone:{brew_id}:{actor.profile_id}".encode()).hexdigest()
    if idempotency_key is not None:
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is not None:
            return replay_idempotent_brew_creation(db, existing, fingerprint)
    if before_create is not None:
        before_create()
    source = load_brew(db, brew_id)
    validate_bloom_water(source.bloom_water_g, source.water_g)
    reserve_available_coffee(db, source.coffee_id)
    try:
        reserve_active_brew_capacity(db)
    except BrewConflictError:
        if idempotency_key is not None:
            existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
            if existing is not None:
                return replay_idempotent_brew_creation(db, existing, fingerprint)
        raise
    clone = Brew(
        coffee_id=source.coffee_id,
        operator_id=actor.profile_id,
        grinder_id=source.grinder_id,
        dripper_id=source.dripper_id,
        filter_id=source.filter_id,
        source_preset_id=source.source_preset_id,
        cloned_from_id=source.id,
        creation_token=idempotency_key,
        creation_request_hash=fingerprint if idempotency_key else None,
        dose_g=source.dose_g,
        water_g=source.water_g,
        target_ratio=source.target_ratio,
        temperature_c=source.temperature_c,
        grinder_setting=source.grinder_setting,
        servings=source.servings,
        target_flow_g_s=source.target_flow_g_s,
        bloom_water_g=source.bloom_water_g,
        bloom_time_s=source.bloom_time_s,
        pour_count=source.pour_count,
        technique_note=source.technique_note,
        status="draft",
        operators=[load_active_operator(db, actor.profile_id)],
    )
    db.add(clone)
    try:
        enqueue_brew_notification(
            db,
            clone,
            "brew_started",
            notifications.public_base_url,
            demo_mode=notifications.demo_mode,
        )
        db.commit()
    except IntegrityError:
        if idempotency_key is None:
            raise
        db.rollback()
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is None:
            raise
        return replay_idempotent_brew_creation(db, existing, fingerprint)
    return load_brew(db, clone.id)


@_rollback_on_failure
def _change_brew_status(
    db: Session, brew_id: int, action: str, payload: BrewStatusChange, actor: BrewActor
) -> Brew:
    if action not in {"cancel", "void"}:
        raise BrewNotFoundError("Unknown action")
    brew = load_brew(db, brew_id)
    expected_status = "completed" if action == "void" else "draft"
    if brew.status != expected_status:
        raise BrewConflictError(
            "Only completed brews can be voided"
            if action == "void"
            else "Only draft brews can be cancelled"
        )
    if action == "void" and not actor.is_admin:
        raise BrewPermissionError("Administrator access required")
    if action == "cancel" and brew.operator_id != actor.profile_id and not actor.is_admin:
        raise BrewPermissionError("Only the operator may cancel this brew")
    return commit_guarded_brew_update(
        db,
        brew.id,
        expected_status,
        actor,
        {"status": "voided" if action == "void" else "cancelled"},
        (
            "Only completed brews can be voided"
            if action == "void"
            else "Only draft brews can be cancelled"
        ),
        "Only the operator may cancel this brew",
        expected_revision=payload.revision,
        release_capacity=action == "cancel",
        before_commit=lambda callback_db, updated_id: cancel_brew_notifications(
            callback_db, updated_id
        ),
    )


def cancel_brew(db: Session, brew_id: int, payload: BrewStatusChange, actor: BrewActor) -> Brew:
    return _change_brew_status(db, brew_id, "cancel", payload, actor)


def void_brew(db: Session, brew_id: int, payload: BrewStatusChange, actor: BrewActor) -> Brew:
    return _change_brew_status(db, brew_id, "void", payload, actor)
