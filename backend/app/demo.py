from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Brew,
    BrewFilter,
    Coffee,
    Dripper,
    FlavorTag,
    Grinder,
    LoginSession,
    Profile,
    RecipePreset,
)

DEMO_PIN = "1234"
DEMO_PROFILE_NAMES = ("Demo Admin", "Alex", "Maya", "Noah")
DEMO_NOTICE = (
    "Public demo: sample data and visitor changes are discarded when the service restarts "
    "and at least once per day. Do not enter personal or confidential information."
)

DEMO_CAPACITIES = {
    "profiles": (20, "profiles"),
    "coffees": (50, "coffees"),
    "grinders": (15, "grinders"),
    "drippers": (15, "drippers"),
    "filters": (15, "filters"),
    "recipe_presets": (20, "recipe presets"),
    "flavor_tags": (80, "flavor tags"),
    "brews": (100, "brews"),
    "ratings": (300, "ratings"),
}

_WINDOW = timedelta(minutes=10)
_CLIENT_WRITE_LIMIT = 60
_GLOBAL_WRITE_LIMIT = 600
_write_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_write_lock = Lock()

_PROTECTED_MODELS = (
    Profile,
    Coffee,
    Grinder,
    Dripper,
    BrewFilter,
    RecipePreset,
    FlavorTag,
    Brew,
)


def is_protected_demo_profile(profile: Profile) -> bool:
    return profile.display_name in DEMO_PROFILE_NAMES


def enforce_demo_write_rate_limit(request: Request) -> None:
    """Bound mutation traffic for a disposable public demo.

    This is deliberately in-memory: free demo instances run one worker and losing the
    counters during a restart is consistent with losing the rest of the demo state.
    """

    if not request.app.state.settings.demo_mode:
        return

    now = datetime.now(UTC)
    window_start = now - _WINDOW
    client = request.client.host if request.client else "unknown"
    keys = (f"client:{client}", "global")
    limits = (_CLIENT_WRITE_LIMIT, _GLOBAL_WRITE_LIMIT)

    with _write_lock:
        for key in keys:
            attempts = _write_attempts[key]
            while attempts and attempts[0] < window_start:
                attempts.popleft()
        if any(len(_write_attempts[key]) >= limit for key, limit in zip(keys, limits, strict=True)):
            raise HTTPException(
                status_code=429,
                detail="The public demo is receiving too many changes. Try again shortly.",
            )
        for key in keys:
            _write_attempts[key].append(now)


def enforce_demo_capacity(request: Request, db: Session, model: type) -> None:
    if not request.app.state.settings.demo_mode:
        return
    limit, label = DEMO_CAPACITIES[model.__tablename__]
    count = db.scalar(select(func.count(model.id))) or 0
    if count >= limit:
        raise HTTPException(
            status_code=409,
            detail=f"The public demo has reached its limit of {limit} {label}.",
        )


def capture_demo_protected_ids(db: Session) -> dict[str, set[int]]:
    """Freeze everything present at startup while leaving visitor-created rows editable."""

    return {model.__tablename__: set(db.scalars(select(model.id))) for model in _PROTECTED_MODELS}


def enforce_demo_seed_protection(request: Request, model: type, item_id: int) -> None:
    if not request.app.state.settings.demo_mode:
        return
    protected = request.app.state.demo_protected_ids.get(model.__tablename__, set())
    if item_id in protected:
        raise HTTPException(
            status_code=403,
            detail="Seeded demo records are read-only; create a new record to experiment.",
        )


def prune_demo_sessions(request: Request, db: Session) -> None:
    if not request.app.state.settings.demo_mode:
        return

    now = datetime.now(UTC)
    expired = list(db.scalars(select(LoginSession).where(LoginSession.expires_at <= now)))
    for item in expired:
        db.delete(item)

    newest = list(db.scalars(select(LoginSession).order_by(LoginSession.created_at.desc())))
    for item in newest[99:]:
        db.delete(item)
    if expired or len(newest) > 99:
        db.commit()
