from __future__ import annotations

import io
from datetime import timedelta

import segno
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import session_dependency, utcnow
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..models import Brew, LoginSession, Profile
from ..schemas.brews import (
    ActiveBrewsResponse,
    BrewCorrection,
    BrewCreate,
    BrewFinalize,
    BrewOperatorUpdate,
    BrewResponse,
    BrewStatusChange,
    BrewUpdate,
)
from ..schemas.ratings import RatingAggregate
from ..security import require_csrf, require_user
from ..services import brews as brew_service
from ..services.brew_types import BrewActor, BrewNotifications
from ..tasting import rating_aggregate
from ._brew_errors import brew_http_errors
from ._brew_support import brew_activity_payload, brew_payload, load_brew
from ._common import effective_public_url, get_settings
from ._rating_support import load_flavor_tags

RECENT_RATING_PROMPT_WINDOW = timedelta(minutes=30)

router = APIRouter()


@router.post("/brews", response_model=BrewResponse)
def create_brew(
    payload: BrewCreate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    confirm_unusual_ratio: bool = Header(default=False, alias="X-Confirm-Unusual-Ratio"),
) -> BrewResponse:
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    notifications = BrewNotifications(
        effective_public_url(request, db), request.app.state.settings.demo_mode
    )
    with brew_http_errors():
        result = brew_service.create_brew(
            db,
            payload,
            actor,
            notifications,
            idempotency_key=idempotency_key,
            confirm_unusual_ratio=confirm_unusual_ratio,
            before_create=lambda: enforce_demo_capacity(request, db, Brew),
        )
    return brew_payload(result, include_token=True)


@router.get("/brews/active", response_model=ActiveBrewsResponse)
def active_brews(db: Session = Depends(session_dependency)) -> ActiveBrewsResponse:
    settings = get_settings(db)
    brews = list(
        db.scalars(
            select(Brew)
            .options(
                selectinload(Brew.coffee),
                selectinload(Brew.operators),
            )
            .where(Brew.status == "draft")
            .order_by(Brew.created_at)
        )
    )
    recent_rating_brews = list(
        db.scalars(
            select(Brew)
            .options(
                selectinload(Brew.coffee),
                selectinload(Brew.operators),
            )
            .where(
                Brew.status == "completed",
                Brew.rating_token.is_not(None),
                Brew.completed_at >= utcnow() - RECENT_RATING_PROMPT_WINDOW,
            )
            .order_by(Brew.completed_at.desc(), Brew.id.desc())
        )
    )
    active_count = len(brews)
    return ActiveBrewsResponse(
        brews=[brew_activity_payload(brew) for brew in brews],
        recent_rating_brews=[
            brew_activity_payload(brew, include_token=True) for brew in recent_rating_brews
        ],
        active_count=active_count,
        max_active_brews=settings.max_active_brews,
        can_start=active_count < settings.max_active_brews,
    )


@router.get("/brews", response_model=list[BrewResponse])
def list_brews(
    coffee_id: int | None = None,
    status: str | None = None,
    exclude_status: str | None = None,
    limit: int = 100,
    db: Session = Depends(session_dependency),
) -> list[BrewResponse]:
    query = (
        select(Brew)
        .options(
            selectinload(Brew.coffee),
            selectinload(Brew.operator),
            selectinload(Brew.operators),
            selectinload(Brew.grinder),
            selectinload(Brew.dripper),
            selectinload(Brew.brew_filter),
        )
        .order_by(Brew.created_at.desc())
        .limit(min(limit, 500))
    )
    if coffee_id is not None:
        query = query.where(Brew.coffee_id == coffee_id)
    if status:
        query = query.where(Brew.status == status)
    if exclude_status:
        query = query.where(Brew.status != exclude_status)
    return [brew_payload(item, include_token=False) for item in db.scalars(query)]


@router.get("/brews/{brew_id}", response_model=BrewResponse)
def get_brew(brew_id: int, db: Session = Depends(session_dependency)) -> BrewResponse:
    return brew_payload(load_brew(db, brew_id), include_token=True)


@router.get("/brews/{brew_id}/rating-insights", response_model=RatingAggregate)
def get_brew_rating_insights(
    brew_id: int,
    db: Session = Depends(session_dependency),
    _viewer: Profile = Depends(require_user),
) -> RatingAggregate:
    brew = load_brew(db, brew_id)
    if brew.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed brews have rating insights")
    return rating_aggregate(brew.ratings, load_flavor_tags(db))


@router.put("/brews/{brew_id}", response_model=BrewResponse)
def update_brew(
    brew_id: int,
    payload: BrewUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
    confirm_unusual_ratio: bool = Header(default=False, alias="X-Confirm-Unusual-Ratio"),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.update_brew(
            db, brew_id, payload, actor, confirm_unusual_ratio=confirm_unusual_ratio
        )
    return brew_payload(result, include_token=True)


@router.post("/brews/{brew_id}/join", response_model=BrewResponse)
def join_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.join_brew(db, brew_id, actor)
    return brew_payload(result, include_token=True)


@router.put("/brews/{brew_id}/operator", response_model=BrewResponse)
def update_brew_operator(
    brew_id: int,
    payload: BrewOperatorUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.update_brew_operator(db, brew_id, payload, actor)
    return brew_payload(result, include_token=True)


@router.put("/brews/{brew_id}/correction", response_model=BrewResponse)
def correct_completed_brew(
    brew_id: int,
    payload: BrewCorrection,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
    confirm_unusual_ratio: bool = Header(default=False, alias="X-Confirm-Unusual-Ratio"),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.correct_completed_brew(
            db, brew_id, payload, actor, confirm_unusual_ratio=confirm_unusual_ratio
        )
    return brew_payload(result, include_token=True)


@router.post("/brews/{brew_id}/finalize", response_model=BrewResponse)
def finalize_brew(
    brew_id: int,
    payload: BrewFinalize,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
    confirm_unusual_ratio: bool = Header(default=False, alias="X-Confirm-Unusual-Ratio"),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    notifications = BrewNotifications(
        effective_public_url(request, db), request.app.state.settings.demo_mode
    )
    with brew_http_errors():
        result = brew_service.finalize_brew(
            db, brew_id, payload, actor, notifications, confirm_unusual_ratio=confirm_unusual_ratio
        )
    return brew_payload(result, include_token=True)


@router.post("/brews/{brew_id}/clone", response_model=BrewResponse)
def clone_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> BrewResponse:
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    notifications = BrewNotifications(
        effective_public_url(request, db), request.app.state.settings.demo_mode
    )
    with brew_http_errors():
        result = brew_service.clone_brew(
            db,
            brew_id,
            actor,
            notifications,
            idempotency_key=idempotency_key,
            before_create=lambda: enforce_demo_capacity(request, db, Brew),
        )
    return brew_payload(result, include_token=True)


@router.post("/brews/{brew_id}/cancel", response_model=BrewResponse)
def cancel_brew(
    brew_id: int,
    payload: BrewStatusChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.cancel_brew(db, brew_id, payload, actor)
    return brew_payload(result, include_token=True)


@router.post("/brews/{brew_id}/void", response_model=BrewResponse)
def void_brew(
    brew_id: int,
    payload: BrewStatusChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    actor = BrewActor(login_session.profile_id, login_session.profile.role == "admin")
    with brew_http_errors():
        result = brew_service.void_brew(db, brew_id, payload, actor)
    return brew_payload(result, include_token=True)


@router.get("/brews/{brew_id}/qr.svg")
def brew_qr(
    brew_id: int, request: Request, db: Session = Depends(session_dependency)
) -> StreamingResponse:
    brew = load_brew(db, brew_id)
    if brew.status != "completed" or not brew.rating_token:
        raise HTTPException(status_code=409, detail="Brew has no active rating link")
    url = f"{effective_public_url(request, db)}/rate/{brew.rating_token}"
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="svg", scale=8, border=4, xmldecl=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )
