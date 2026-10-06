"""Coffee commands own commits and roll back failed changes.

Automatic colour allocation and the surrounding coffee write share a transaction.
Callers supply authenticated profile IDs and any creation policy; HTTP checks and
photo handling stay in the transport and catalog photo modules.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..coffee_colors import next_coffee_color
from ..db import utcnow
from ..models import AppSettings, Coffee
from ..schemas.coffees import CoffeeInput
from ._transactions import rollback_on_failure
from .coffee_errors import CoffeeConflictError, CoffeeNotFoundError, CoffeePermissionError


def _automatic_coffee_color(
    db: Session, coffee_id: int | None = None, excluded: tuple[str, ...] = ()
) -> str:
    # Hold SQLite's writer lock until the surrounding coffee write commits.
    # Explicit user-selected colours may still be shared between bags.
    db.execute(text("UPDATE app_settings SET id = id WHERE id = 1"))
    settings = db.get(AppSettings, 1, populate_existing=True)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.flush()
    query = select(Coffee.chart_color)
    if coffee_id is not None:
        query = query.where(Coffee.id != coffee_id)
    return next_coffee_color(db.scalars(query), excluded=excluded, surface=settings.color_surface)


def _coffee_creation_fingerprint(payload: CoffeeInput) -> str:
    canonical_payload = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_payload.encode()).hexdigest()


def _replay_idempotent_coffee_creation(
    coffee: Coffee, request_fingerprint: str, profile_id: int
) -> Coffee:
    if coffee.created_by_id == profile_id and coffee.creation_request_hash == request_fingerprint:
        return coffee
    raise CoffeeConflictError(
        "Idempotency key was already used for a different coffee creation request"
    )


def _load_coffee(db: Session, coffee_id: int) -> Coffee:
    coffee = db.get(Coffee, coffee_id, populate_existing=True)
    if coffee is None:
        raise CoffeeNotFoundError("Coffee not found")
    return coffee


@rollback_on_failure
def create_coffee(
    db: Session,
    payload: CoffeeInput,
    profile_id: int,
    *,
    idempotency_key: str | None = None,
    before_create: Callable[[], None] | None = None,
) -> Coffee:
    request_fingerprint = _coffee_creation_fingerprint(payload)
    if idempotency_key is not None:
        existing = db.scalar(
            select(Coffee)
            .where(Coffee.creation_token == idempotency_key)
            .execution_options(populate_existing=True)
        )
        if existing is not None:
            return _replay_idempotent_coffee_creation(existing, request_fingerprint, profile_id)
    if before_create is not None:
        before_create()
    coffee = Coffee(
        **payload.model_dump(exclude={"chart_color"}),
        chart_color=payload.chart_color or _automatic_coffee_color(db),
        created_by_id=profile_id,
        creation_token=idempotency_key,
        creation_request_hash=request_fingerprint if idempotency_key else None,
    )
    db.add(coffee)
    try:
        db.commit()
    except IntegrityError:
        if idempotency_key is None:
            raise
        db.rollback()
        existing = db.scalar(
            select(Coffee)
            .where(Coffee.creation_token == idempotency_key)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            raise
        return _replay_idempotent_coffee_creation(existing, request_fingerprint, profile_id)
    db.refresh(coffee)
    return coffee


@rollback_on_failure
def update_coffee(db: Session, coffee_id: int, payload: CoffeeInput) -> Coffee:
    coffee = _load_coffee(db, coffee_id)
    for key, value in payload.model_dump(exclude={"chart_color"}).items():
        setattr(coffee, key, value)
    if "chart_color" in payload.model_fields_set:
        coffee.chart_color = payload.chart_color or _automatic_coffee_color(db, coffee_id=coffee.id)
    db.commit()
    db.refresh(coffee)
    return coffee


@rollback_on_failure
def archive_coffee(db: Session, coffee_id: int, *, is_admin: bool) -> Coffee:
    if not is_admin:
        raise CoffeePermissionError("Administrator access required")
    coffee = _load_coffee(db, coffee_id)
    coffee.archived = True
    db.commit()
    db.refresh(coffee)
    return coffee


@rollback_on_failure
def finish_coffee(db: Session, coffee_id: int) -> Coffee:
    coffee = _load_coffee(db, coffee_id)
    if coffee.archived:
        raise CoffeeConflictError("Archived coffee cannot be marked finished")
    if coffee.finished_at is None:
        coffee.finished_at = utcnow()
        db.commit()
        db.refresh(coffee)
    return coffee


@rollback_on_failure
def restore_coffee(db: Session, coffee_id: int) -> Coffee:
    coffee = _load_coffee(db, coffee_id)
    if coffee.archived:
        raise CoffeeConflictError("Archived coffee cannot be restored")
    if coffee.finished_at is not None:
        coffee.finished_at = None
        db.commit()
        db.refresh(coffee)
    return coffee


@rollback_on_failure
def clone_coffee(
    db: Session,
    coffee_id: int,
    profile_id: int,
    *,
    before_create: Callable[[], None] | None = None,
) -> Coffee:
    if before_create is not None:
        before_create()
    source = _load_coffee(db, coffee_id)
    clone = Coffee(
        roaster=source.roaster,
        name=source.name,
        country=source.country,
        region=source.region,
        producer=source.producer,
        purchase_location=source.purchase_location,
        process=source.process,
        roast_level=source.roast_level,
        variety=source.variety,
        package_notes=source.package_notes,
        chart_color=_automatic_coffee_color(db, excluded=(source.chart_color,)),
        cloned_from_id=source.id,
        created_by_id=profile_id,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone
