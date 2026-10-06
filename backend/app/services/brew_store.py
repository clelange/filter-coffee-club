from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.orm import Session, selectinload

from ..models import AppSettings, Brew, Coffee, Profile, Rating, brew_operators
from .brew_errors import (
    BrewConflictError,
    BrewNotFoundError,
    BrewPermissionError,
    BrewValidationError,
)
from .brew_types import BrewActor


def conflict_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def replay_idempotent_brew_creation(db: Session, brew: Brew, request_fingerprint: str) -> Brew:
    if brew.creation_request_hash == request_fingerprint:
        return load_brew(db, brew.id)
    raise BrewConflictError(
        "Idempotency key was already used for a different brew creation request"
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
        raise BrewValidationError("Coffee not found")
    raise BrewConflictError(
        conflict_detail("coffee_unavailable", "Coffee is no longer available for brewing")
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
        raise BrewNotFoundError("Brew not found")
    return brew


def load_active_operator(db: Session, operator_id: int) -> Profile:
    operator = db.get(Profile, operator_id)
    if operator is None:
        raise BrewNotFoundError("Operator not found")
    if not operator.active:
        raise BrewValidationError("Operator must be active")
    return operator


def is_brew_operator(brew: Brew, profile_id: int) -> bool:
    return any(operator.id == profile_id for operator in brew.operators)


def reserve_active_brew_capacity(db: Session) -> None:
    if db.get(AppSettings, 1) is None:
        db.add(AppSettings(id=1))
        db.flush()
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
        raise BrewConflictError(
            conflict_detail(
                "brew_capacity_reached", "The maximum number of parallel brews is already active"
            )
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
    actor: BrewActor,
    values: dict[str, object],
    status_detail: str,
    permission_detail: str,
    expected_revision: int | None = None,
    allow_collaborators: bool = False,
    release_capacity: bool = False,
    before_commit: Callable[[Session, int], None] | None = None,
    operators: list[Profile] | None = None,
) -> Brew:
    conditions = [Brew.id == brew_id, Brew.status == expected_status]
    allow_collaborators = allow_collaborators and operators is None
    if expected_revision is not None:
        conditions.append(Brew.revision == expected_revision)
    if not actor.is_admin:
        if allow_collaborators:
            conditions.append(
                Brew.id.in_(
                    select(brew_operators.c.brew_id).where(
                        brew_operators.c.profile_id == actor.profile_id
                    )
                )
            )
        else:
            conditions.append(Brew.operator_id == actor.profile_id)
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
            raise BrewConflictError(status_detail)
        if not actor.is_admin and (
            current.operator_id != actor.profile_id
            if not allow_collaborators
            else not is_brew_operator(current, actor.profile_id)
        ):
            raise BrewPermissionError(permission_detail)
        if expected_revision is not None and current.revision != expected_revision:
            raise BrewConflictError("Brew changed; refresh and try again")
        raise BrewConflictError("Brew changed; refresh and try again")
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
    return load_brew(db, updated_id)
