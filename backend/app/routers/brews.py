from __future__ import annotations

import hashlib
import io
import secrets
from datetime import timedelta

import segno
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db import session_dependency, utcnow
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..mattermost import cancel_brew_notifications, enqueue_brew_notification
from ..models import Brew, LoginSession, Profile, brew_operators
from ..schemas import (
    ActiveBrewsResponse,
    BrewCorrection,
    BrewCreate,
    BrewFinalize,
    BrewOperatorUpdate,
    BrewResponse,
    BrewStatusChange,
    BrewUpdate,
    RatingAggregate,
)
from ..security import require_csrf, require_user
from ..tasting import rating_aggregate
from ._brew_support import (
    brew_activity_payload,
    brew_creation_fingerprint,
    brew_payload,
    changed_brewers,
    commit_guarded_brew_update,
    is_brew_operator,
    load_active_operator,
    load_brew,
    log_unusual_brew_ratio,
    replay_idempotent_brew_creation,
    reserve_active_brew_capacity,
    reserve_available_coffee,
    selected_brewers,
    validate_bloom_water,
    validate_brew_ratio,
)
from ._common import effective_public_url, get_settings
from ._equipment import validate_grinder_setting
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
    request_fingerprint = brew_creation_fingerprint(payload, login_session.profile_id)
    if idempotency_key is not None:
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is not None:
            return replay_idempotent_brew_creation(db, existing, request_fingerprint)
    enforce_demo_capacity(request, db, Brew)
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
    except HTTPException:
        if idempotency_key is not None:
            existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
            if existing is not None:
                return replay_idempotent_brew_creation(db, existing, request_fingerprint)
        raise
    operators = selected_brewers(
        db,
        payload.operator_ids or [login_session.profile_id],
        login_session.profile_id,
        [login_session.profile],
    )
    brew = Brew(
        **payload.model_dump(exclude={"operator_ids"}),
        operator_id=login_session.profile_id,
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
            effective_public_url(request, db),
            demo_mode=request.app.state.settings.demo_mode,
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
    result = brew_payload(load_brew(db, brew.id), include_token=True)
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
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft brews can be edited")
    if (
        not is_brew_operator(brew, login_session.profile_id)
        and login_session.profile.role != "admin"
    ):
        raise HTTPException(status_code=403, detail="Only a brew operator may edit this draft")
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
        login_session,
        payload.model_dump(exclude={"revision", "operator_ids"}),
        "Only draft brews can be edited",
        "Only a brew operator may edit this draft",
        expected_revision=payload.revision,
        allow_collaborators=True,
        operators=changed_brewers(db, brew, payload.operator_ids, login_session),
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


@router.post("/brews/{brew_id}/join", response_model=BrewResponse)
def join_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only active brews can be joined")
    if is_brew_operator(brew, login_session.profile_id):
        return brew_payload(brew, include_token=True)
    joined_id = db.scalar(
        update(Brew)
        .where(
            Brew.id == brew.id,
            Brew.status == "draft",
            ~Brew.id.in_(
                select(brew_operators.c.brew_id).where(
                    brew_operators.c.profile_id == login_session.profile_id
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
            raise HTTPException(status_code=409, detail="Only active brews can be joined")
        if is_brew_operator(current, login_session.profile_id):
            return brew_payload(current, include_token=True)
        raise HTTPException(status_code=409, detail="Brew changed; refresh and try again")
    db.execute(
        insert(brew_operators).values(
            brew_id=brew.id,
            profile_id=login_session.profile_id,
        )
    )
    db.commit()
    return brew_payload(load_brew(db, brew.id), include_token=True)


@router.put("/brews/{brew_id}/operator", response_model=BrewResponse)
def update_brew_operator(
    brew_id: int,
    payload: BrewOperatorUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft brews can change operator")
    if brew.operator_id != login_session.profile_id and login_session.profile.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only the operator or an administrator may reassign this brew",
        )
    operator = load_active_operator(db, payload.operator_id)
    if not is_brew_operator(brew, operator.id):
        db.execute(insert(brew_operators).values(brew_id=brew.id, profile_id=operator.id))
    return commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        login_session,
        {"operator_id": operator.id},
        "Only draft brews can change operator",
        "Only the operator or an administrator may reassign this brew",
        expected_revision=payload.revision,
    )


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
    brew = load_brew(db, brew_id)
    if brew.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed brews need correction")
    if brew.operator_id != login_session.profile_id and login_session.profile.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only the operator or an administrator may correct this brew",
        )
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
    operators = changed_brewers(db, brew, payload.operator_ids, login_session, payload.operator_id)
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
        login_session,
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
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft brews can be finalized")
    if (
        not is_brew_operator(brew, login_session.profile_id)
        and login_session.profile.role != "admin"
    ):
        raise HTTPException(status_code=403, detail="Only a brew operator may finalize this brew")
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
        login_session,
        values,
        "Only draft brews can be finalized",
        "Only a brew operator may finalize this brew",
        expected_revision=payload.revision,
        allow_collaborators=True,
        operators=changed_brewers(db, brew, payload.operator_ids, login_session),
        release_capacity=True,
        before_commit=lambda callback_db, updated_id: enqueue_brew_notification(
            callback_db,
            load_brew(callback_db, updated_id),
            "ready_to_rate",
            effective_public_url(request, callback_db),
            demo_mode=request.app.state.settings.demo_mode,
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
    fingerprint = hashlib.sha256(f"clone:{brew_id}:{login_session.profile_id}".encode()).hexdigest()
    if idempotency_key is not None:
        existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
        if existing is not None:
            return replay_idempotent_brew_creation(db, existing, fingerprint)
    enforce_demo_capacity(request, db, Brew)
    source = load_brew(db, brew_id)
    validate_bloom_water(source.bloom_water_g, source.water_g)
    reserve_available_coffee(db, source.coffee_id)
    try:
        reserve_active_brew_capacity(db)
    except HTTPException:
        if idempotency_key is not None:
            existing = db.scalar(select(Brew).where(Brew.creation_token == idempotency_key))
            if existing is not None:
                return replay_idempotent_brew_creation(db, existing, fingerprint)
        raise
    clone = Brew(
        coffee_id=source.coffee_id,
        operator_id=login_session.profile_id,
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
        operators=[login_session.profile],
    )
    db.add(clone)
    try:
        enqueue_brew_notification(
            db,
            clone,
            "brew_started",
            effective_public_url(request, db),
            demo_mode=request.app.state.settings.demo_mode,
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
    return brew_payload(load_brew(db, clone.id), include_token=True)


def _change_brew_status(
    brew_id: int,
    action: str,
    payload: BrewStatusChange,
    request: Request,
    db: Session,
    login_session: LoginSession,
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    if action not in {"cancel", "void"}:
        raise HTTPException(status_code=404, detail="Unknown action")
    brew = load_brew(db, brew_id)
    expected_status = "completed" if action == "void" else "draft"
    if brew.status != expected_status:
        raise HTTPException(
            status_code=409,
            detail=(
                "Only completed brews can be voided"
                if action == "void"
                else "Only draft brews can be cancelled"
            ),
        )
    if action == "void" and login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    if (
        action == "cancel"
        and brew.operator_id != login_session.profile_id
        and login_session.profile.role != "admin"
    ):
        raise HTTPException(status_code=403, detail="Only the operator may cancel this brew")
    return commit_guarded_brew_update(
        db,
        brew.id,
        expected_status,
        login_session,
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


@router.post("/brews/{brew_id}/cancel", response_model=BrewResponse)
def cancel_brew(
    brew_id: int,
    payload: BrewStatusChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    return _change_brew_status(brew_id, "cancel", payload, request, db, login_session)


@router.post("/brews/{brew_id}/void", response_model=BrewResponse)
def void_brew(
    brew_id: int,
    payload: BrewStatusChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    return _change_brew_status(brew_id, "void", payload, request, db, login_session)


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
