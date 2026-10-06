from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..catalog_photos import (
    remove_catalog_photo,
    save_catalog_photo,
    update_catalog_photo_framing,
)
from ..db import session_dependency
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..models import Brew, Coffee, LoginSession, Profile, Rating
from ..schemas.coffees import CoffeeInput, CoffeeResponse
from ..schemas.photos import PhotoFramingUpdate
from ..schemas.ratings import CoffeeRatingInsights, RatedBrewInsight
from ..security import require_csrf, require_personal_csrf, require_user
from ..services import coffees as coffee_service
from ..tasting import MIN_RANKING_RATINGS, ranked_brew_ids, rating_aggregate
from ._brew_support import brew_payload, load_brew
from ._catalog_photos import (
    catalog_photo_http_errors,
    ensure_catalog_photo_writes_allowed,
    photo_framing_tuple,
    uploaded_photo_framing,
)
from ._coffee_errors import coffee_http_errors
from ._rating_support import load_flavor_tags

router = APIRouter()


@router.get("/coffees", response_model=list[CoffeeResponse])
def list_coffees(
    include_archived: bool = False,
    include_finished: bool = False,
    db: Session = Depends(session_dependency),
) -> list[Coffee]:
    query = select(Coffee).order_by(
        Coffee.archived, Coffee.finished_at.is_not(None), Coffee.roaster, Coffee.name
    )
    if include_archived:
        return list(db.scalars(query))
    query = query.where(Coffee.archived.is_(False))
    if not include_finished:
        query = query.where(Coffee.finished_at.is_(None))
    return list(db.scalars(query))


@router.post("/coffees", response_model=CoffeeResponse)
def create_coffee(
    payload: CoffeeInput,
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
) -> Coffee:
    with coffee_http_errors():
        return coffee_service.create_coffee(
            db,
            payload,
            login_session.profile_id,
            idempotency_key=idempotency_key,
            before_create=lambda: enforce_demo_capacity(request, db, Coffee),
        )


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
                selectinload(Brew.operators),
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
    ranked_ids = ranked_brew_ids(all_ratings)
    best = load_brew(db, ranked_ids[0]) if ranked_ids else None
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
        taster_count=len({rating.profile_id for rating in all_ratings}),
        ranking_min_ratings=MIN_RANKING_RATINGS,
        best_brew=(
            RatedBrewInsight(
                brew=brew_payload(best), aggregate=rating_aggregate(best.ratings, flavor_tags)
            )
            if best is not None
            else None
        ),
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
    with coffee_http_errors():
        return coffee_service.update_coffee(db, coffee_id, payload)


@router.put("/coffees/{coffee_id}/photo", response_model=CoffeeResponse)
async def put_coffee_photo(
    coffee_id: int,
    photo: UploadFile,
    request: Request,
    focus_x: float | None = Form(default=None, ge=0, le=1),
    focus_y: float | None = Form(default=None, ge=0, le=1),
    zoom: float | None = Form(default=None, ge=1, le=3),
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Coffee:
    ensure_catalog_photo_writes_allowed(request)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    framing = uploaded_photo_framing(focus_x, focus_y, zoom)
    settings = request.app.state.settings
    content = await photo.read(settings.max_catalog_photo_bytes + 1)
    with catalog_photo_http_errors():
        await save_catalog_photo(content, settings, db, coffee, framing)
    return coffee


@router.patch("/coffees/{coffee_id}/photo", response_model=CoffeeResponse)
def patch_coffee_photo_framing(
    coffee_id: int,
    payload: PhotoFramingUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Coffee:
    ensure_catalog_photo_writes_allowed(request)
    coffee = db.get(Coffee, coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404, detail="Coffee not found")
    with catalog_photo_http_errors():
        update_catalog_photo_framing(db, coffee, photo_framing_tuple(payload.photo_framing))
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
    with coffee_http_errors():
        return coffee_service.archive_coffee(
            db, coffee_id, is_admin=login_session.profile.role == "admin"
        )


@router.post("/coffees/{coffee_id}/finish", response_model=CoffeeResponse)
def finish_coffee(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Coffee:
    enforce_demo_seed_protection(request, Coffee, coffee_id)
    with coffee_http_errors():
        return coffee_service.finish_coffee(db, coffee_id)


@router.post("/coffees/{coffee_id}/restore", response_model=CoffeeResponse)
def restore_coffee(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Coffee:
    enforce_demo_seed_protection(request, Coffee, coffee_id)
    with coffee_http_errors():
        return coffee_service.restore_coffee(db, coffee_id)


@router.post("/coffees/{coffee_id}/clone", response_model=CoffeeResponse)
def clone_coffee(
    coffee_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Coffee:
    with coffee_http_errors():
        return coffee_service.clone_coffee(
            db,
            coffee_id,
            login_session.profile_id,
            before_create=lambda: enforce_demo_capacity(request, db, Coffee),
        )
