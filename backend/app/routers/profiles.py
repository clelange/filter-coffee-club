from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from ..db import session_dependency
from ..demo import enforce_demo_capacity, is_protected_demo_profile
from ..models import Brew, Coffee, LoginSession, Profile, Rating
from ..schemas import (
    ProfileCoffeePreference,
    ProfileCreate,
    ProfileDirectoryItem,
    ProfileIdentity,
    ProfilePublic,
    ProfileRatingsResponse,
    ProfileUpdate,
)
from ..security import clear_login_failures, hash_pin, require_admin, require_csrf, require_user
from ..tasting import RATING_FIELDS
from ._rating_support import profile_rating_result

router = APIRouter()


def reserve_admin_removal(db: Session, profile_id: int, payload: ProfileUpdate) -> None:
    """Prevent concurrent profile changes from removing the last active administrator."""

    if payload.role != "member" and payload.active is not False:
        return
    another_active_admin = (
        select(Profile.id)
        .where(
            Profile.id != profile_id,
            Profile.role == "admin",
            Profile.active.is_(True),
        )
        .exists()
    )
    reserved_id = db.scalar(
        update(Profile)
        .where(
            Profile.id == profile_id,
            or_(
                Profile.role != "admin",
                Profile.active.is_(False),
                another_active_admin,
            ),
        )
        .values(role=Profile.role)
        .returning(Profile.id)
        .execution_options(synchronize_session=False)
    )
    if reserved_id is not None:
        return
    db.rollback()
    if db.get(Profile, profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    raise HTTPException(
        status_code=409,
        detail="At least one active administrator must remain",
    )


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
    except IntegrityError as exc:
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
    reserve_admin_removal(db, profile_id, payload)
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


def profile_rating_filters(profile_id: int, viewer: Profile) -> tuple[bool, list]:
    complete_history = viewer.id == profile_id or viewer.role == "admin"
    filters = [Rating.profile_id == profile_id, Brew.status == "completed"]
    if not complete_history:
        viewer_rating = aliased(Rating)
        shared_brew_ids = select(viewer_rating.brew_id).where(viewer_rating.profile_id == viewer.id)
        filters.append(Brew.id.in_(shared_brew_ids))
    return complete_history, filters


@router.get("/profiles", response_model=list[ProfileDirectoryItem])
def list_profiles(
    db: Session = Depends(session_dependency), viewer: Profile = Depends(require_user)
) -> list[ProfileDirectoryItem]:
    profiles = list(
        db.scalars(select(Profile).where(Profile.active.is_(True)).order_by(Profile.display_name))
    )
    if not profiles:
        return []

    count_filters = [
        Rating.profile_id.in_([profile.id for profile in profiles]),
        Brew.status == "completed",
    ]
    if viewer.role != "admin":
        viewer_rating = aliased(Rating)
        shared_brew_ids = select(viewer_rating.brew_id).where(viewer_rating.profile_id == viewer.id)
        count_filters.append(or_(Rating.profile_id == viewer.id, Brew.id.in_(shared_brew_ids)))
    count_rows = db.execute(
        select(Rating.profile_id, func.count(Rating.id))
        .join(Rating.brew)
        .where(*count_filters)
        .group_by(Rating.profile_id)
    )
    counts = {profile_id: rating_count for profile_id, rating_count in count_rows}

    return [
        ProfileDirectoryItem(
            id=profile.id,
            display_name=profile.display_name,
            is_self=profile.id == viewer.id,
            is_complete_history=profile.id == viewer.id or viewer.role == "admin",
            rating_count=counts.get(profile.id, 0),
        )
        for profile in profiles
    ]


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

    complete_history, filters = profile_rating_filters(profile.id, viewer)

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
        profile=ProfileIdentity.model_validate(profile),
        is_self=viewer.id == profile.id,
        is_complete_history=complete_history,
        rating_count=rating_count,
        averages=profile_averages,
        favorite_coffees=favorite_coffees,
        ratings=[profile_rating_result(item) for item in target_ratings],
        next_offset=next_offset if next_offset < rating_count else None,
    )
