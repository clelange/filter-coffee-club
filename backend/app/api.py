from __future__ import annotations

import csv
import io
import json
import logging
import secrets
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased, selectinload

from .calculations import brew_ratio, overall_throughput
from .catalog_photos import remove_catalog_photo, save_catalog_photo
from .db import session_dependency, utcnow
from .demo import (
    DEMO_NOTICE,
    DEMO_PIN,
    DEMO_PROFILE_NAMES,
    enforce_demo_capacity,
    enforce_demo_seed_protection,
    enforce_demo_write_rate_limit,
    is_protected_demo_profile,
    prune_demo_sessions,
)
from .models import (
    AppSettings,
    Brew,
    BrewFilter,
    Coffee,
    Dripper,
    FlavorTag,
    Grinder,
    LoginSession,
    PresetGrinderRange,
    Profile,
    Rating,
    RecipePreset,
)
from .schemas import (
    AppSettingsResponse,
    AppSettingsUpdate,
    BootstrapInput,
    BrewCorrection,
    BrewFinalize,
    BrewInput,
    BrewOperatorUpdate,
    BrewResponse,
    CatalogBrewResult,
    CatalogInsights,
    CatalogKind,
    CatalogUsageItem,
    CatalogUsageResponse,
    CoffeeInput,
    CoffeeRatingInsights,
    CoffeeResponse,
    DripperResponse,
    EquipmentInput,
    FilterInput,
    FilterResponse,
    FlavorAxisSummary,
    FlavorTagInput,
    FlavorTagResponse,
    GrinderInput,
    GrinderResponse,
    LoginInput,
    PinChange,
    PresetResponse,
    PresetUpdate,
    ProfileCoffeePreference,
    ProfileCreate,
    ProfilePublic,
    ProfileRatingResult,
    ProfileRatingsResponse,
    ProfileUpdate,
    RatedBrewInsight,
    RatingAggregate,
    RatingComparison,
    RatingInput,
    RatingItem,
    RatingLinkResponse,
    RatingSummary,
    SessionResponse,
)
from .security import (
    clear_login_failures,
    create_login_session,
    hash_pin,
    login_attempt_guard,
    login_retry_after,
    optional_login_session,
    record_login_failure,
    require_admin,
    require_csrf,
    require_csrf_token,
    require_login_session,
    require_personal_csrf,
    require_user,
    verify_pin,
    verify_profile_pin,
)

router = APIRouter(prefix="/api/v1")
RATING_FIELDS = ("liking", "acidity", "bitterness", "sweetness", "body")


def ensure_catalog_photo_writes_allowed(request: Request) -> None:
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="Photo changes are disabled in demo mode")


auth_logger = logging.getLogger("fcc.auth")


def session_payload(login_session: LoginSession) -> SessionResponse:
    return SessionResponse(
        profile=ProfilePublic.model_validate(login_session.profile),
        csrf_token=login_session.csrf_token,
        device_mode=login_session.device_mode,
        expires_at=login_session.expires_at,
    )


def set_session_cookie(request: Request, response: Response, raw: str, hours: int) -> None:
    response.set_cookie(
        request.app.state.settings.session_cookie,
        raw,
        max_age=hours * 3600,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def uses_integer_clicks(grinder: Grinder) -> bool:
    return grinder.setting_unit.strip().lower() in {"click", "clicks"}


def validate_grinder_setting(db: Session, grinder_id: int, setting: float) -> None:
    grinder = db.get(Grinder, grinder_id)
    if grinder is None:
        raise HTTPException(status_code=422, detail="Grinder not found")
    if uses_integer_clicks(grinder) and not float(setting).is_integer():
        raise HTTPException(
            status_code=422,
            detail="Grinder click settings must be whole numbers",
        )


def validate_preset_grinder_ranges(db: Session, payload: PresetUpdate) -> None:
    for grinder_range in payload.grinder_ranges:
        grinder = db.get(Grinder, grinder_range.grinder_id)
        if grinder is None:
            raise HTTPException(status_code=422, detail="Grinder not found")
        if uses_integer_clicks(grinder) and not (
            float(grinder_range.setting_min).is_integer()
            and float(grinder_range.setting_max).is_integer()
        ):
            raise HTTPException(
                status_code=422,
                detail="Preset click ranges must use whole numbers",
            )


def effective_public_url(request: Request, db: Session) -> str:
    row = get_settings(db)
    stored_url = None if request.app.state.settings.demo_mode else row.public_base_url
    configured = (stored_url or request.app.state.settings.public_base_url or "").strip()
    return configured.rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"


def brew_payload(brew: Brew, include_token: bool = False) -> BrewResponse:
    ratio = brew_ratio(brew.water_g, brew.dose_g)
    throughput = overall_throughput(brew.water_g, brew.total_brew_time_s)
    return BrewResponse(
        id=brew.id,
        coffee_id=brew.coffee_id,
        operator_id=brew.operator_id,
        grinder_id=brew.grinder_id,
        dripper_id=brew.dripper_id,
        filter_id=brew.filter_id,
        source_preset_id=brew.source_preset_id,
        cloned_from_id=brew.cloned_from_id,
        dose_g=brew.dose_g,
        water_g=brew.water_g,
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


def load_brew(db: Session, brew_id: int) -> Brew:
    brew = db.scalar(
        select(Brew)
        .options(
            selectinload(Brew.coffee),
            selectinload(Brew.operator),
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


def commit_guarded_brew_update(
    db: Session,
    brew_id: int,
    expected_status: str,
    login_session: LoginSession,
    values: dict[str, object],
    status_detail: str,
    permission_detail: str,
) -> BrewResponse:
    conditions = [Brew.id == brew_id, Brew.status == expected_status]
    if login_session.profile.role != "admin":
        conditions.append(Brew.operator_id == login_session.profile_id)
    updated_id = db.scalar(
        update(Brew)
        .where(*conditions)
        .values(**values)
        .returning(Brew.id)
        .execution_options(synchronize_session=False)
    )
    if updated_id is None:
        db.rollback()
        current = load_brew(db, brew_id)
        if current.status != expected_status:
            raise HTTPException(status_code=409, detail=status_detail)
        if (
            login_session.profile.role != "admin"
            and current.operator_id != login_session.profile_id
        ):
            raise HTTPException(status_code=403, detail=permission_detail)
        raise HTTPException(status_code=409, detail="Brew changed; refresh and try again")
    db.commit()
    return brew_payload(load_brew(db, updated_id), include_token=True)


def rating_item(rating: Rating) -> RatingItem:
    return RatingItem(
        profile_id=rating.profile_id,
        profile_name=rating.profile.display_name,
        liking=rating.liking,
        acidity=rating.acidity,
        bitterness=rating.bitterness,
        sweetness=rating.sweetness,
        body=rating.body,
        flavor_tag_ids=[tag.id for tag in rating.flavor_tags],
        updated_at=rating.updated_at,
    )


def load_flavor_tags(db: Session) -> list[FlavorTag]:
    return list(
        db.scalars(
            select(FlavorTag).order_by(FlavorTag.parent_id, FlavorTag.sort_order, FlavorTag.name)
        )
    )


def rating_aggregate(ratings: list[Rating], flavor_tags: list[FlavorTag]) -> RatingAggregate:
    active_parents = sorted(
        (tag for tag in flavor_tags if tag.active and tag.parent_id is None),
        key=lambda tag: (tag.sort_order, tag.name),
    )
    active_parent_ids = {tag.id for tag in active_parents}
    category_by_tag_id = {
        tag.id: tag.id if tag.parent_id is None else tag.parent_id for tag in flavor_tags
    }
    mentions: Counter[int] = Counter()
    for rating in ratings:
        mentioned_categories = {
            category_id
            for tag in rating.flavor_tags
            if (category_id := category_by_tag_id.get(tag.id)) in active_parent_ids
        }
        mentions.update(mentioned_categories)
    averages = (
        {
            field: round(mean(getattr(rating, field) for rating in ratings), 2)
            for field in RATING_FIELDS
        }
        if ratings
        else {}
    )
    return RatingAggregate(
        count=len(ratings),
        averages=averages,
        flavor_axes=[
            FlavorAxisSummary(
                id=parent.id,
                label=parent.name,
                mentions=mentions[parent.id],
                total=len(ratings),
            )
            for parent in active_parents
        ],
    )


def rating_summary(brew: Brew, viewer: Profile, db: Session) -> RatingSummary:
    own = next((rating for rating in brew.ratings if rating.profile_id == viewer.id), None)
    can_view = own is not None or viewer.role == "admin"
    if not can_view:
        return RatingSummary(can_view=False, own_rating=None)
    ratings = [rating_item(item) for item in brew.ratings]
    aggregate = rating_aggregate(brew.ratings, load_flavor_tags(db))
    flavor_counts = Counter(tag.name for item in brew.ratings for tag in item.flavor_tags)
    return RatingSummary(
        can_view=True,
        own_rating=rating_item(own) if own else None,
        ratings=ratings,
        count=aggregate.count,
        averages=aggregate.averages,
        flavor_counts=dict(flavor_counts.most_common()),
        flavor_axes=aggregate.flavor_axes,
    )


def rating_comparison(target_rating: Rating) -> RatingComparison:
    peer_ratings = [
        item for item in target_rating.brew.ratings if item.profile_id != target_rating.profile_id
    ]
    peer_averages = (
        {
            field: round(mean(getattr(item, field) for item in peer_ratings), 2)
            for field in RATING_FIELDS
        }
        if peer_ratings
        else {}
    )
    peer_flavor_counts = Counter(tag.name for item in peer_ratings for tag in item.flavor_tags)
    return RatingComparison(
        brew_id=target_rating.brew_id,
        rating=rating_item(target_rating),
        total_rating_count=len(target_rating.brew.ratings),
        peer_count=len(peer_ratings),
        peer_averages=peer_averages,
        peer_deltas=(
            {
                field: round(getattr(target_rating, field) - peer_averages[field], 2)
                for field in RATING_FIELDS
            }
            if peer_ratings
            else {}
        ),
        selected_flavors=sorted(tag.name for tag in target_rating.flavor_tags),
        peer_flavor_counts=dict(peer_flavor_counts.most_common()),
    )


def profile_rating_result(target_rating: Rating) -> ProfileRatingResult:
    return ProfileRatingResult(
        **rating_comparison(target_rating).model_dump(),
        brew=brew_payload(target_rating.brew, include_token=False),
    )


@router.get("/auth/bootstrap-status")
def bootstrap_status(
    request: Request, db: Session = Depends(session_dependency)
) -> dict[str, bool]:
    if request.app.state.settings.demo_mode:
        return {"required": False}
    return {"required": (db.scalar(select(func.count(Profile.id))) or 0) == 0}


@router.post("/auth/bootstrap", response_model=SessionResponse)
def bootstrap(
    payload: BootstrapInput,
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
) -> SessionResponse:
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="First-run setup is disabled in demo mode")
    if (db.scalar(select(func.count(Profile.id))) or 0) > 0:
        raise HTTPException(status_code=409, detail="Initial setup is already complete")
    profile = Profile(
        display_name=payload.display_name.strip(),
        pin_hash=hash_pin(payload.pin),
        role="admin",
        pin_change_required=False,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    hours = (
        request.app.state.settings.personal_session_hours
        if payload.device_mode == "personal"
        else request.app.state.settings.kiosk_session_hours
    )
    raw, login_session = create_login_session(db, profile, payload.device_mode, hours)
    set_session_cookie(request, response, raw, hours)
    return session_payload(login_session)


@router.get("/auth/profiles", response_model=list[ProfilePublic])
def list_public_profiles(db: Session = Depends(session_dependency)) -> list[Profile]:
    return list(
        db.scalars(select(Profile).where(Profile.active.is_(True)).order_by(Profile.display_name))
    )


@router.post(
    "/auth/login",
    response_model=SessionResponse,
    responses={
        429: {
            "description": "Login temporarily blocked after repeated failures",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until another login attempt is allowed",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
) -> SessionResponse:
    enforce_demo_write_rate_limit(request)
    profile = db.get(Profile, payload.profile_id)
    with login_attempt_guard(profile.id if profile is not None else None):
        if profile is not None:
            db.rollback()
            profile = db.get(Profile, payload.profile_id)
        throttle_exempt = bool(
            profile and request.app.state.settings.demo_mode and is_protected_demo_profile(profile)
        )
        retry_after = (
            0
            if profile is None or not profile.active or throttle_exempt
            else login_retry_after(profile)
        )
        if retry_after:
            auth_logger.warning(
                "login_backoff",
                extra={
                    "fields": {
                        "profile_id": payload.profile_id,
                        "failure_count": profile.failed_login_attempts,
                        "retry_after_seconds": retry_after,
                    }
                },
            )
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        if not verify_profile_pin(profile, payload.pin):
            attempts = 0
            delay = 0
            if profile is not None and profile.active and not throttle_exempt:
                attempts, delay = record_login_failure(db, profile)
            auth_logger.warning(
                "login_failure",
                extra={
                    "fields": {
                        "profile_id": payload.profile_id,
                        "failure_count": attempts or None,
                        "retry_after_seconds": delay,
                    }
                },
            )
            if delay:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Try again shortly.",
                    headers={"Retry-After": str(delay)},
                )
            raise HTTPException(status_code=401, detail="Invalid profile or PIN")
        assert profile is not None
        clear_login_failures(profile)
        prune_demo_sessions(request, db)
        hours = (
            request.app.state.settings.personal_session_hours
            if payload.device_mode == "personal"
            else request.app.state.settings.kiosk_session_hours
        )
        raw, login_session = create_login_session(db, profile, payload.device_mode, hours)
        set_session_cookie(request, response, raw, hours)
        return session_payload(login_session)


@router.get("/auth/me", response_model=SessionResponse)
def me(login_session: LoginSession = Depends(require_login_session)) -> SessionResponse:
    return session_payload(login_session)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf_token),
) -> None:
    db.delete(login_session)
    db.commit()
    response.delete_cookie(request.app.state.settings.session_cookie, path="/")


@router.post("/auth/pin", status_code=204)
def change_pin(
    payload: PinChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf_token),
) -> None:
    profile = login_session.profile
    if request.app.state.settings.demo_mode and is_protected_demo_profile(profile):
        raise HTTPException(status_code=403, detail="Demo profile credentials are fixed")
    if not verify_pin(profile.pin_hash, payload.current_pin):
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")
    if verify_pin(profile.pin_hash, payload.new_pin):
        raise HTTPException(
            status_code=400, detail="New PIN must be different from the current PIN"
        )
    profile.pin_hash = hash_pin(payload.new_pin)
    profile.pin_change_required = False
    clear_login_failures(profile)
    db.commit()


@router.get("/people", response_model=list[ProfilePublic])
def list_people(
    _admin: Profile = Depends(require_admin), db: Session = Depends(session_dependency)
) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.display_name)))


@router.post("/people", response_model=ProfilePublic)
def create_person(
    payload: ProfileCreate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Profile:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_capacity(request, db, Profile)
    profile = Profile(
        display_name=payload.display_name.strip(),
        pin_hash=hash_pin(payload.pin),
        role=payload.role,
        pin_change_required=True,
    )
    db.add(profile)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Display name is already in use") from exc
    db.refresh(profile)
    return profile


@router.put("/people/{profile_id}", response_model=ProfilePublic)
def update_person(
    profile_id: int,
    payload: ProfileUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Profile:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if request.app.state.settings.demo_mode and is_protected_demo_profile(profile):
        raise HTTPException(status_code=403, detail="Seeded demo profiles cannot be changed")
    reactivating = payload.active is True and not profile.active
    for key, value in payload.model_dump(exclude_unset=True, exclude={"pin"}).items():
        setattr(profile, key, value)
    if payload.pin:
        profile.pin_hash = hash_pin(payload.pin)
    if payload.pin or reactivating:
        clear_login_failures(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/coffees", response_model=list[CoffeeResponse])
def list_coffees(
    include_archived: bool = False, db: Session = Depends(session_dependency)
) -> list[Coffee]:
    query = select(Coffee).order_by(Coffee.archived, Coffee.roaster, Coffee.name)
    if not include_archived:
        query = query.where(Coffee.archived.is_(False))
    return list(db.scalars(query))


@router.post("/coffees", response_model=CoffeeResponse)
def create_coffee(
    payload: CoffeeInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Coffee:
    enforce_demo_capacity(request, db, Coffee)
    coffee = Coffee(**payload.model_dump(), created_by_id=login_session.profile_id)
    db.add(coffee)
    db.commit()
    db.refresh(coffee)
    return coffee


@router.get("/coffees/{coffee_id}", response_model=CoffeeResponse)
def get_coffee(coffee_id: int, db: Session = Depends(session_dependency)) -> Coffee:
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    return coffee


@router.get("/coffees/{coffee_id}/rating-insights", response_model=CoffeeRatingInsights)
def get_coffee_rating_insights(
    coffee_id: int,
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(session_dependency),
    _viewer: Profile = Depends(require_user),
) -> CoffeeRatingInsights:
    if db.get(Coffee, coffee_id) is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    all_ratings = list(
        db.scalars(
            select(Rating)
            .join(Rating.brew)
            .options(selectinload(Rating.flavor_tags))
            .where(Brew.coffee_id == coffee_id, Brew.status == "completed")
        )
    )
    rated_brew_count = (
        db.scalar(
            select(func.count(Brew.id)).where(
                Brew.coffee_id == coffee_id,
                Brew.status == "completed",
                Brew.ratings.any(),
            )
        )
        or 0
    )
    page = list(
        db.scalars(
            select(Brew)
            .options(
                selectinload(Brew.coffee),
                selectinload(Brew.operator),
                selectinload(Brew.grinder),
                selectinload(Brew.dripper),
                selectinload(Brew.brew_filter),
                selectinload(Brew.ratings).selectinload(Rating.flavor_tags),
            )
            .where(
                Brew.coffee_id == coffee_id,
                Brew.status == "completed",
                Brew.ratings.any(),
            )
            .order_by(Brew.completed_at.desc(), Brew.created_at.desc(), Brew.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    flavor_tags = load_flavor_tags(db)
    next_offset = offset + len(page) if offset + len(page) < rated_brew_count else None
    return CoffeeRatingInsights(
        coffee_id=coffee_id,
        aggregate=rating_aggregate(all_ratings, flavor_tags),
        rated_brew_count=rated_brew_count,
        rated_brews=[
            RatedBrewInsight(
                brew=brew_payload(brew, include_token=False),
                aggregate=rating_aggregate(brew.ratings, flavor_tags),
            )
            for brew in page
        ],
        next_offset=next_offset,
    )


@router.put("/coffees/{coffee_id}", response_model=CoffeeResponse)
def update_coffee(
    coffee_id: int,
    payload: CoffeeInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Coffee:
    enforce_demo_seed_protection(request, Coffee, coffee_id)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    for key, value in payload.model_dump().items():
        setattr(coffee, key, value)
    db.commit()
    db.refresh(coffee)
    return coffee


@router.put("/coffees/{coffee_id}/photo", response_model=CoffeeResponse)
async def put_coffee_photo(
    coffee_id: int,
    photo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Coffee:
    ensure_catalog_photo_writes_allowed(request)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    await save_catalog_photo(photo, request.app.state.settings, db, coffee)
    return coffee


@router.delete("/coffees/{coffee_id}/photo", response_model=CoffeeResponse)
def delete_coffee_photo(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Coffee:
    ensure_catalog_photo_writes_allowed(request)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    remove_catalog_photo(request.app.state.settings, db, coffee)
    return coffee


@router.post("/coffees/{coffee_id}/archive", response_model=CoffeeResponse)
def archive_coffee(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Coffee:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, Coffee, coffee_id)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    coffee.archived = True
    db.commit()
    db.refresh(coffee)
    return coffee


@router.post("/coffees/{coffee_id}/clone", response_model=CoffeeResponse)
def clone_coffee(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Coffee:
    enforce_demo_capacity(request, db, Coffee)
    source = db.get(Coffee, coffee_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    clone = Coffee(
        roaster=source.roaster,
        name=source.name,
        country=source.country,
        region=source.region,
        producer=source.producer,
        process=source.process,
        roast_level=source.roast_level,
        variety=source.variety,
        package_notes=source.package_notes,
        cloned_from_id=source.id,
        created_by_id=login_session.profile_id,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.get("/grinders", response_model=list[GrinderResponse])
def list_grinders(db: Session = Depends(session_dependency)) -> list[Grinder]:
    return list(
        db.scalars(select(Grinder).where(Grinder.archived.is_(False)).order_by(Grinder.model))
    )


@router.post("/grinders", response_model=GrinderResponse)
def create_grinder(
    payload: GrinderInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Grinder:
    enforce_demo_capacity(request, db, Grinder)
    item = Grinder(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/grinders/{item_id}", response_model=GrinderResponse)
def get_grinder(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> Grinder:
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    return item


@router.put("/grinders/{item_id}", response_model=GrinderResponse)
def update_grinder(
    item_id: int,
    payload: GrinderInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Grinder:
    enforce_demo_seed_protection(request, Grinder, item_id)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/grinders/{item_id}/photo", response_model=GrinderResponse)
async def put_grinder_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Grinder:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    await save_catalog_photo(photo, request.app.state.settings, db, item)
    return item


@router.delete("/grinders/{item_id}/photo", response_model=GrinderResponse)
def delete_grinder_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Grinder:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    remove_catalog_photo(request.app.state.settings, db, item)
    return item


@router.post("/grinders/{item_id}/archive", response_model=GrinderResponse)
def archive_grinder(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Grinder:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, Grinder, item_id)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item


@router.get("/drippers", response_model=list[DripperResponse])
def list_drippers(db: Session = Depends(session_dependency)) -> list[Dripper]:
    return list(
        db.scalars(select(Dripper).where(Dripper.archived.is_(False)).order_by(Dripper.model))
    )


@router.post("/drippers", response_model=DripperResponse)
def create_dripper(
    payload: EquipmentInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Dripper:
    enforce_demo_capacity(request, db, Dripper)
    item = Dripper(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/drippers/{item_id}", response_model=DripperResponse)
def get_dripper(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> Dripper:
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    return item


@router.put("/drippers/{item_id}", response_model=DripperResponse)
def update_dripper(
    item_id: int,
    payload: EquipmentInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Dripper:
    enforce_demo_seed_protection(request, Dripper, item_id)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/drippers/{item_id}/photo", response_model=DripperResponse)
async def put_dripper_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Dripper:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    await save_catalog_photo(photo, request.app.state.settings, db, item)
    return item


@router.delete("/drippers/{item_id}/photo", response_model=DripperResponse)
def delete_dripper_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Dripper:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    remove_catalog_photo(request.app.state.settings, db, item)
    return item


@router.post("/drippers/{item_id}/archive", response_model=DripperResponse)
def archive_dripper(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Dripper:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, Dripper, item_id)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item


@router.get("/filters", response_model=list[FilterResponse])
def list_filters(db: Session = Depends(session_dependency)) -> list[BrewFilter]:
    return list(
        db.scalars(
            select(BrewFilter).where(BrewFilter.archived.is_(False)).order_by(BrewFilter.name)
        )
    )


@router.post("/filters", response_model=FilterResponse)
def create_filter(
    payload: FilterInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    enforce_demo_capacity(request, db, BrewFilter)
    item = BrewFilter(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/filters/{item_id}", response_model=FilterResponse)
def get_filter(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> BrewFilter:
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    return item


@router.put("/filters/{item_id}", response_model=FilterResponse)
def update_filter(
    item_id: int,
    payload: FilterInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    enforce_demo_seed_protection(request, BrewFilter, item_id)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/filters/{item_id}/photo", response_model=FilterResponse)
async def put_filter_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> BrewFilter:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    await save_catalog_photo(photo, request.app.state.settings, db, item)
    return item


@router.delete("/filters/{item_id}/photo", response_model=FilterResponse)
def delete_filter_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> BrewFilter:
    ensure_catalog_photo_writes_allowed(request)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    remove_catalog_photo(request.app.state.settings, db, item)
    return item


@router.post("/filters/{item_id}/archive", response_model=FilterResponse)
def archive_filter(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, BrewFilter, item_id)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item


def catalog_target(kind: CatalogKind, item_id: int, db: Session) -> tuple[object, object]:
    if kind == "coffee":
        item = db.get(Coffee, item_id)
        brew_filter = Brew.coffee_id == item_id
        missing = "Coffee not found"
    elif kind == "grinder":
        item = db.get(Grinder, item_id)
        brew_filter = Brew.grinder_id == item_id
        missing = "Grinder not found"
    elif kind == "dripper":
        item = db.get(Dripper, item_id)
        brew_filter = Brew.dripper_id == item_id
        missing = "Dripper not found"
    else:
        item = db.get(BrewFilter, item_id)
        brew_filter = Brew.filter_id == item_id
        missing = "Filter not found"
    if item is None:
        raise HTTPException(status_code=404, detail=missing)
    return item, brew_filter


def rounded_mean(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(mean(present), 2) if present else None


@router.get("/catalog/usage", response_model=CatalogUsageResponse)
def catalog_usage(db: Session = Depends(session_dependency)) -> CatalogUsageResponse:
    items: list[CatalogUsageItem] = []
    columns = (
        ("coffee", Brew.coffee_id),
        ("grinder", Brew.grinder_id),
        ("dripper", Brew.dripper_id),
        ("filter", Brew.filter_id),
    )
    for kind, column in columns:
        rows = db.execute(
            select(column, func.count(Brew.id), func.max(Brew.completed_at))
            .where(Brew.status == "completed", column.is_not(None))
            .group_by(column)
            .order_by(column)
        )
        items.extend(
            CatalogUsageItem(
                kind=kind,
                item_id=item_id,
                completed_brew_count=count,
                last_completed_at=last_completed_at,
            )
            for item_id, count, last_completed_at in rows
        )
    return CatalogUsageResponse(items=items)


@router.get("/catalog/{kind}/{item_id}/insights", response_model=CatalogInsights)
def catalog_insights(
    kind: CatalogKind,
    item_id: int,
    limit: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(session_dependency),
    login_session: LoginSession | None = Depends(optional_login_session),
) -> CatalogInsights:
    if kind != "coffee" and login_session is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    _item, item_filter = catalog_target(kind, item_id, db)
    brews = list(
        db.scalars(
            select(Brew)
            .options(
                selectinload(Brew.coffee),
                selectinload(Brew.operator),
                selectinload(Brew.grinder),
                selectinload(Brew.dripper),
                selectinload(Brew.brew_filter),
                selectinload(Brew.ratings),
            )
            .where(Brew.status == "completed", item_filter)
            .order_by(Brew.completed_at.desc(), Brew.created_at.desc())
        )
    )
    ratings_visible = bool(
        login_session is not None and not login_session.profile.pin_change_required
    )
    all_ratings = [rating for brew in brews for rating in brew.ratings]
    recent_brews = []
    for brew in brews[:limit]:
        ratings = brew.ratings if ratings_visible else []
        recent_brews.append(
            CatalogBrewResult(
                **brew_payload(brew, include_token=False).model_dump(),
                rating_count=len(ratings) if ratings_visible else None,
                average_liking=(
                    rounded_mean([rating.liking for rating in ratings]) if ratings_visible else None
                ),
            )
        )
    throughputs = [overall_throughput(brew.water_g, brew.total_brew_time_s) for brew in brews]
    settings = [brew.grinder_setting for brew in brews] if kind == "grinder" else []
    return CatalogInsights(
        kind=kind,
        item_id=item_id,
        completed_brew_count=len(brews),
        last_completed_at=max(
            (brew.completed_at for brew in brews if brew.completed_at is not None),
            default=None,
        ),
        average_ratio=rounded_mean([brew_ratio(brew.water_g, brew.dose_g) for brew in brews]),
        average_temperature_c=rounded_mean([brew.temperature_c for brew in brews]),
        average_total_brew_time_s=rounded_mean([brew.total_brew_time_s for brew in brews]),
        average_overall_throughput_g_s=rounded_mean(throughputs),
        observed_grinder_setting_min=min(settings, default=None),
        observed_grinder_setting_max=max(settings, default=None),
        ratings_visible=ratings_visible,
        rating_count=len(all_ratings) if ratings_visible else None,
        average_liking=(
            rounded_mean([rating.liking for rating in all_ratings]) if ratings_visible else None
        ),
        recent_brews=recent_brews,
    )


@router.get("/presets", response_model=list[PresetResponse])
def list_presets(
    active_only: bool = True, db: Session = Depends(session_dependency)
) -> list[RecipePreset]:
    query = (
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .order_by(RecipePreset.sort_order)
    )
    if active_only:
        query = query.where(RecipePreset.active.is_(True))
    return list(db.scalars(query))


@router.put("/presets/{preset_id}", response_model=PresetResponse)
def update_preset(
    preset_id: int,
    payload: PresetUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> RecipePreset:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, RecipePreset, preset_id)
    item = db.get(RecipePreset, preset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    validate_preset_grinder_ranges(db, payload)
    for key, value in payload.model_dump(exclude={"grinder_ranges"}).items():
        setattr(item, key, value)
    item.grinder_ranges.clear()
    for grinder_range in payload.grinder_ranges:
        item.grinder_ranges.append(PresetGrinderRange(**grinder_range.model_dump()))
    db.commit()
    return db.scalar(
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .where(RecipePreset.id == preset_id)
    )


@router.post("/presets", response_model=PresetResponse)
def create_preset(
    payload: PresetUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> RecipePreset:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_capacity(request, db, RecipePreset)
    validate_preset_grinder_ranges(db, payload)
    item = RecipePreset(**payload.model_dump(exclude={"grinder_ranges"}))
    item.grinder_ranges = [
        PresetGrinderRange(**grinder_range.model_dump()) for grinder_range in payload.grinder_ranges
    ]
    db.add(item)
    db.commit()
    return db.scalar(
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .where(RecipePreset.id == item.id)
    )


@router.get("/flavor-tags", response_model=list[FlavorTagResponse])
def list_flavor_tags(
    active_only: bool = True, db: Session = Depends(session_dependency)
) -> list[FlavorTag]:
    query = select(FlavorTag).order_by(FlavorTag.parent_id, FlavorTag.sort_order, FlavorTag.name)
    if active_only:
        query = query.where(FlavorTag.active.is_(True))
    return list(db.scalars(query))


@router.post("/flavor-tags", response_model=FlavorTagResponse)
def create_flavor_tag(
    payload: FlavorTagInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> FlavorTag:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_capacity(request, db, FlavorTag)
    item = FlavorTag(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/flavor-tags/{tag_id}", response_model=FlavorTagResponse)
def update_flavor_tag(
    tag_id: int,
    payload: FlavorTagInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> FlavorTag:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, FlavorTag, tag_id)
    item = db.get(FlavorTag, tag_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Flavor tag not found")
    if payload.parent_id == item.id:
        raise HTTPException(status_code=422, detail="A tag cannot be its own parent")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/brews", response_model=BrewResponse)
def create_brew(
    payload: BrewInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_capacity(request, db, Brew)
    validate_grinder_setting(db, payload.grinder_id, payload.grinder_setting)
    brew = Brew(**payload.model_dump(), operator_id=login_session.profile_id)
    db.add(brew)
    db.commit()
    return brew_payload(load_brew(db, brew.id), include_token=True)


@router.get("/brews", response_model=list[BrewResponse])
def list_brews(
    coffee_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(session_dependency),
) -> list[BrewResponse]:
    query = (
        select(Brew)
        .options(
            selectinload(Brew.coffee),
            selectinload(Brew.operator),
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
    payload: BrewInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft brews can be edited")
    if brew.operator_id != login_session.profile_id and login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Only the operator may edit this draft")
    validate_grinder_setting(db, payload.grinder_id, payload.grinder_setting)
    return commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        login_session,
        payload.model_dump(),
        "Only draft brews can be edited",
        "Only the operator may edit this draft",
    )


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
    return commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        login_session,
        {"operator_id": operator.id},
        "Only draft brews can change operator",
        "Only the operator or an administrator may reassign this brew",
    )


@router.put("/brews/{brew_id}/correction", response_model=BrewResponse)
def correct_completed_brew(
    brew_id: int,
    payload: BrewCorrection,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
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
    values: dict[str, object] = payload.model_dump(exclude={"operator_id"})
    if payload.operator_id is not None:
        values["operator_id"] = load_active_operator(db, payload.operator_id).id
    return commit_guarded_brew_update(
        db,
        brew.id,
        "completed",
        login_session,
        values,
        "Only completed brews need correction",
        "Only the operator or an administrator may correct this brew",
    )


@router.post("/brews/{brew_id}/finalize", response_model=BrewResponse)
def finalize_brew(
    brew_id: int,
    payload: BrewFinalize,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_seed_protection(request, Brew, brew_id)
    brew = load_brew(db, brew_id)
    if brew.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft brews can be finalized")
    if brew.operator_id != login_session.profile_id and login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Only the operator may finalize this brew")
    values: dict[str, object] = {
        "total_brew_time_s": payload.total_brew_time_s,
        "status": "completed",
        "completed_at": utcnow(),
        "rating_token": secrets.token_urlsafe(24),
    }
    if payload.water_g is not None:
        values["water_g"] = payload.water_g
    return commit_guarded_brew_update(
        db,
        brew.id,
        "draft",
        login_session,
        values,
        "Only draft brews can be finalized",
        "Only the operator may finalize this brew",
    )


@router.post("/brews/{brew_id}/clone", response_model=BrewResponse)
def clone_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    enforce_demo_capacity(request, db, Brew)
    source = load_brew(db, brew_id)
    clone = Brew(
        coffee_id=source.coffee_id,
        operator_id=login_session.profile_id,
        grinder_id=source.grinder_id,
        dripper_id=source.dripper_id,
        filter_id=source.filter_id,
        source_preset_id=source.source_preset_id,
        cloned_from_id=source.id,
        dose_g=source.dose_g,
        water_g=source.water_g,
        temperature_c=source.temperature_c,
        grinder_setting=source.grinder_setting,
        servings=source.servings,
        target_flow_g_s=source.target_flow_g_s,
        bloom_water_g=source.bloom_water_g,
        bloom_time_s=source.bloom_time_s,
        pour_count=source.pour_count,
        technique_note=source.technique_note,
        status="draft",
    )
    db.add(clone)
    db.commit()
    return brew_payload(load_brew(db, clone.id), include_token=True)


def _change_brew_status(
    brew_id: int,
    action: str,
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
    )


@router.post("/brews/{brew_id}/cancel", response_model=BrewResponse)
def cancel_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    return _change_brew_status(brew_id, "cancel", request, db, login_session)


@router.post("/brews/{brew_id}/void", response_model=BrewResponse)
def void_brew(
    brew_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewResponse:
    return _change_brew_status(brew_id, "void", request, db, login_session)


@router.get("/rating-links/{token}", response_model=RatingLinkResponse)
def resolve_rating_link(
    token: str, db: Session = Depends(session_dependency)
) -> RatingLinkResponse:
    brew = db.scalar(select(Brew).where(Brew.rating_token == token))
    if brew is None:
        raise HTTPException(status_code=404, detail="Rating link not found")
    loaded = load_brew(db, brew.id)
    if loaded.status != "completed":
        return RatingLinkResponse(active=False, brew=None)
    return RatingLinkResponse(active=True, brew=brew_payload(loaded, include_token=False))


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


@router.get("/brews/{brew_id}/ratings", response_model=RatingSummary)
def get_ratings(
    brew_id: int,
    db: Session = Depends(session_dependency),
    viewer: Profile = Depends(require_user),
) -> RatingSummary:
    return rating_summary(load_brew(db, brew_id), viewer, db)


@router.get("/profiles/{profile_id}/ratings", response_model=ProfileRatingsResponse)
def get_profile_ratings(
    profile_id: int,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(session_dependency),
    viewer: Profile = Depends(require_user),
) -> ProfileRatingsResponse:
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    complete_history = viewer.id == profile.id or viewer.role == "admin"
    filters = [Rating.profile_id == profile.id, Brew.status == "completed"]
    if not complete_history:
        viewer_rating = aliased(Rating)
        shared_brew_ids = select(viewer_rating.brew_id).where(viewer_rating.profile_id == viewer.id)
        filters.append(Brew.id.in_(shared_brew_ids))

    rating_count = db.scalar(select(func.count(Rating.id)).join(Rating.brew).where(*filters)) or 0
    average_row = db.execute(
        select(*(func.avg(getattr(Rating, field)) for field in RATING_FIELDS))
        .join(Rating.brew)
        .where(*filters)
    ).one()
    profile_averages = (
        {field: round(float(average_row[index]), 2) for index, field in enumerate(RATING_FIELDS)}
        if rating_count
        else {}
    )

    favorite_count = func.count(Rating.id).label("rating_count")
    favorite_average = func.avg(Rating.liking).label("average_liking")
    favorite_rows = db.execute(
        select(
            Coffee.id,
            Coffee.name,
            Coffee.roaster,
            favorite_count,
            favorite_average,
        )
        .select_from(Rating)
        .join(Rating.brew)
        .join(Coffee, Coffee.id == Brew.coffee_id)
        .where(*filters)
        .group_by(Coffee.id, Coffee.name, Coffee.roaster)
        .order_by(
            favorite_average.desc(),
            favorite_count.desc(),
            func.lower(Coffee.roaster),
            func.lower(Coffee.name),
        )
        .limit(3)
    ).all()
    favorite_coffees = [
        ProfileCoffeePreference(
            coffee_id=row.id,
            coffee_name=row.name,
            coffee_roaster=row.roaster,
            rating_count=row.rating_count,
            average_liking=round(float(row.average_liking), 2),
        )
        for row in favorite_rows
    ]

    target_ratings = list(
        db.scalars(
            select(Rating)
            .join(Rating.brew)
            .options(
                selectinload(Rating.profile),
                selectinload(Rating.flavor_tags),
                selectinload(Rating.brew).selectinload(Brew.coffee),
                selectinload(Rating.brew).selectinload(Brew.operator),
                selectinload(Rating.brew).selectinload(Brew.grinder),
                selectinload(Rating.brew).selectinload(Brew.dripper),
                selectinload(Rating.brew).selectinload(Brew.brew_filter),
                selectinload(Rating.brew)
                .selectinload(Brew.ratings)
                .selectinload(Rating.flavor_tags),
            )
            .where(*filters)
            .order_by(Brew.completed_at.desc(), Rating.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    next_offset = offset + len(target_ratings)

    return ProfileRatingsResponse(
        profile=ProfilePublic.model_validate(profile),
        is_self=viewer.id == profile.id,
        is_complete_history=complete_history,
        rating_count=rating_count,
        averages=profile_averages,
        favorite_coffees=favorite_coffees,
        ratings=[profile_rating_result(item) for item in target_ratings],
        next_offset=next_offset if next_offset < rating_count else None,
    )


@router.get("/ratings/me/comparisons", response_model=list[RatingComparison])
def get_my_rating_comparisons(
    brew_id: list[int] = Query(...),
    db: Session = Depends(session_dependency),
    viewer: Profile = Depends(require_user),
) -> list[RatingComparison]:
    if not 1 <= len(brew_id) <= 50:
        raise HTTPException(status_code=422, detail="Provide between 1 and 50 brew IDs")
    if len(brew_id) != len(set(brew_id)):
        raise HTTPException(status_code=422, detail="Brew IDs must be unique")
    if any(item <= 0 for item in brew_id):
        raise HTTPException(status_code=422, detail="Brew IDs must be positive")

    ratings = list(
        db.scalars(
            select(Rating)
            .join(Rating.brew)
            .options(
                selectinload(Rating.profile),
                selectinload(Rating.flavor_tags),
                selectinload(Rating.brew)
                .selectinload(Brew.ratings)
                .selectinload(Rating.flavor_tags),
            )
            .where(
                Rating.profile_id == viewer.id,
                Rating.brew_id.in_(brew_id),
                Brew.status == "completed",
            )
        )
    )
    ratings_by_brew = {item.brew_id: item for item in ratings}
    return [rating_comparison(ratings_by_brew[item]) for item in brew_id if item in ratings_by_brew]


@router.post("/brews/{brew_id}/ratings", response_model=RatingSummary)
def submit_rating(
    brew_id: int,
    payload: RatingInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> RatingSummary:
    enforce_demo_seed_protection(request, Brew, brew_id)
    brew = load_brew(db, brew_id)
    if brew.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed brews can be rated")
    tags = list(
        db.scalars(
            select(FlavorTag).where(
                FlavorTag.id.in_(payload.flavor_tag_ids), FlavorTag.active.is_(True)
            )
        )
    )
    if len(tags) != len(payload.flavor_tag_ids):
        raise HTTPException(status_code=422, detail="One or more flavor tags are invalid")
    rating = db.scalar(
        select(Rating).where(
            Rating.brew_id == brew.id, Rating.profile_id == login_session.profile_id
        )
    )
    values = payload.model_dump(exclude={"flavor_tag_ids"})
    if rating is None:
        enforce_demo_capacity(request, db, Rating)
        rating = Rating(brew_id=brew.id, profile_id=login_session.profile_id, **values)
        db.add(rating)
    else:
        for key, value in values.items():
            setattr(rating, key, value)
    rating.flavor_tags = tags
    db.commit()
    return rating_summary(load_brew(db, brew.id), login_session.profile, db)


@router.get("/analytics")
def analytics(
    db: Session = Depends(session_dependency), _viewer: Profile = Depends(require_user)
) -> dict:
    brews = list(
        db.scalars(
            select(Brew)
            .options(
                selectinload(Brew.coffee),
                selectinload(Brew.operator),
                selectinload(Brew.grinder),
                selectinload(Brew.ratings).selectinload(Rating.flavor_tags),
            )
            .where(Brew.status == "completed")
            .order_by(Brew.completed_at)
        )
    )
    all_ratings = [rating for brew in brews for rating in brew.ratings]
    coffee_scores: dict[int, list[int]] = defaultdict(list)
    coffee_names: dict[int, str] = {}
    for brew in brews:
        coffee_names[brew.coffee_id] = f"{brew.coffee.roaster} · {brew.coffee.name}"
        coffee_scores[brew.coffee_id].extend(rating.liking for rating in brew.ratings)
    top_coffees = [
        {
            "coffee_id": coffee_id,
            "name": coffee_names[coffee_id],
            "average": round(mean(scores), 2),
            "ratings": len(scores),
        }
        for coffee_id, scores in coffee_scores.items()
        if len(scores) >= 3
    ]
    top_coffees.sort(key=lambda item: (-item["average"], -item["ratings"]))
    top_recipes = [
        {
            "brew_id": brew.id,
            "name": f"{brew.coffee.roaster} · {brew.coffee.name}",
            "recipe": (
                f"1:{brew_ratio(brew.water_g, brew.dose_g)} · "
                f"{brew.temperature_c:g} °C · {brew.grinder_setting:g} "
                f"{brew.grinder.setting_unit}"
            ),
            "average": round(mean(rating.liking for rating in brew.ratings), 2),
            "ratings": len(brew.ratings),
        }
        for brew in brews
        if len(brew.ratings) >= 3
    ]
    top_recipes.sort(key=lambda item: (-item["average"], -item["ratings"]))
    flavor_counts = Counter(tag.name for rating in all_ratings for tag in rating.flavor_tags)
    operator_counts = Counter(brew.operator.display_name for brew in brews)
    scatter = []
    for brew in brews:
        if not brew.ratings:
            continue
        scatter.append(
            {
                "brew_id": brew.id,
                "coffee_id": brew.coffee_id,
                "coffee": coffee_names[brew.coffee_id],
                "liking": round(mean(rating.liking for rating in brew.ratings), 2),
                "ratings": len(brew.ratings),
                "ratio": round(brew.water_g / brew.dose_g, 2),
                "temperature_c": brew.temperature_c,
                "grinder_id": brew.grinder_id,
                "grinder_name": f"{brew.grinder.manufacturer} {brew.grinder.model}",
                "grinder_setting": brew.grinder_setting,
                "total_brew_time_s": brew.total_brew_time_s,
                "target_flow_g_s": brew.target_flow_g_s,
            }
        )
    return {
        "counts": {"brews": len(brews), "ratings": len(all_ratings), "coffees": len(coffee_scores)},
        "top_coffees": top_coffees[:10],
        "top_recipes": top_recipes[:10],
        "flavor_counts": dict(flavor_counts.most_common(12)),
        "operator_counts": dict(operator_counts.most_common()),
        "scatter": scatter,
    }


@router.get("/settings", response_model=AppSettingsResponse)
def public_settings(
    request: Request, db: Session = Depends(session_dependency)
) -> AppSettingsResponse:
    item = get_settings(db)
    result = AppSettingsResponse.model_validate(item)
    url = effective_public_url(request, db)
    result.public_base_url = url
    result.public_url_needs_configuration = url in {
        "http://filter-coffee-club.local",
        "http://localhost:8000",
    }
    if request.app.state.settings.demo_mode:
        result.demo_mode = True
        result.demo_notice = DEMO_NOTICE
        result.demo_pin = DEMO_PIN
        result.demo_profile_names = list(DEMO_PROFILE_NAMES)
    return result


@router.put("/settings", response_model=AppSettingsResponse)
def update_settings(
    payload: AppSettingsUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    if request.app.state.settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Branding is read-only in demo mode",
        )
    item = get_settings(db)
    excluded = {"public_base_url"} if request.app.state.settings.demo_mode else set()
    for key, value in payload.model_dump(exclude=excluded).items():
        setattr(item, key, value.rstrip("/") if key == "public_base_url" and value else value)
    if request.app.state.settings.demo_mode:
        item.public_base_url = None
    db.commit()
    return public_settings(request, db)


@router.post("/settings/logo", response_model=AppSettingsResponse)
async def upload_logo(
    logo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="Logo uploads are disabled in demo mode")
    allowed = {"image/png": ".png", "image/webp": ".webp"}
    if logo.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Logo must be PNG or WebP")
    content = await logo.read(request.app.state.settings.max_logo_bytes + 1)
    if len(content) > request.app.state.settings.max_logo_bytes:
        raise HTTPException(status_code=413, detail="Logo exceeds 2 MB")
    is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if (logo.content_type == "image/png" and not is_png) or (
        logo.content_type == "image/webp" and not is_webp
    ):
        raise HTTPException(status_code=415, detail="Logo contents do not match its file type")
    filename = f"logo-{secrets.token_hex(8)}{allowed[logo.content_type]}"
    path: Path = request.app.state.settings.upload_dir / filename
    path.write_bytes(content)
    item = get_settings(db)
    item.logo_path = f"/uploads/{filename}"
    db.commit()
    return public_settings(request, db)


def export_rows(db: Session) -> dict[str, list[dict]]:
    coffees = [
        {
            "id": item.id,
            "roaster": item.roaster,
            "name": item.name,
            "country": item.country,
            "region": item.region,
            "producer": item.producer,
            "process": item.process,
            "roast_level": item.roast_level,
            "roast_date": item.roast_date,
            "opened_date": item.opened_date,
            "variety": item.variety,
            "package_notes": item.package_notes,
            "archived": item.archived,
        }
        for item in db.scalars(select(Coffee).order_by(Coffee.id))
    ]
    brews = []
    for item in db.scalars(select(Brew).order_by(Brew.id)):
        brews.append(
            {
                "id": item.id,
                "coffee_id": item.coffee_id,
                "operator_id": item.operator_id,
                "grinder_id": item.grinder_id,
                "dripper_id": item.dripper_id,
                "filter_id": item.filter_id,
                "dose_g": item.dose_g,
                "water_g": item.water_g,
                "ratio": round(item.water_g / item.dose_g, 2),
                "temperature_c": item.temperature_c,
                "grinder_setting": item.grinder_setting,
                "servings": item.servings,
                "target_flow_g_s": item.target_flow_g_s,
                "total_brew_time_s": item.total_brew_time_s,
                "bloom_water_g": item.bloom_water_g,
                "bloom_time_s": item.bloom_time_s,
                "pour_count": item.pour_count,
                "technique_note": item.technique_note,
                "status": item.status,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
        )
    ratings = []
    for item in db.scalars(
        select(Rating).options(selectinload(Rating.flavor_tags)).order_by(Rating.id)
    ):
        ratings.append(
            {
                "id": item.id,
                "brew_id": item.brew_id,
                "profile_id": item.profile_id,
                "liking": item.liking,
                "acidity": item.acidity,
                "bitterness": item.bitterness,
                "sweetness": item.sweetness,
                "body": item.body,
                "flavor_tags": "; ".join(tag.name for tag in item.flavor_tags),
                "created_at": item.created_at,
            }
        )
    return {"coffees": coffees, "brews": brews, "ratings": ratings}


@router.get("/exports/json")
def export_json(
    db: Session = Depends(session_dependency), _admin: Profile = Depends(require_admin)
) -> JSONResponse:
    return JSONResponse(
        content=json.loads(json.dumps(export_rows(db), default=str)),
        headers={"Content-Disposition": "attachment; filename=fcc-export.json"},
    )


@router.get("/exports/csv")
def export_csv(
    db: Session = Depends(session_dependency), _admin: Profile = Depends(require_admin)
) -> StreamingResponse:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name, rows in export_rows(db).items():
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            zip_file.writestr(f"{name}.csv", output.getvalue())
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=fcc-csv-export.zip"},
    )
