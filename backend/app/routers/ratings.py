from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import session_dependency
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..models import Brew, FlavorTag, LoginSession, Profile, Rating
from ..schemas import RatingComparison, RatingInput, RatingLinkResponse, RatingSummary
from ..security import require_csrf, require_user
from ._brew_support import brew_payload, load_brew
from ._rating_support import rating_comparison, rating_summary

router = APIRouter()


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


@router.get("/brews/{brew_id}/ratings", response_model=RatingSummary)
def get_ratings(
    brew_id: int,
    db: Session = Depends(session_dependency),
    viewer: Profile = Depends(require_user),
) -> RatingSummary:
    return rating_summary(load_brew(db, brew_id), viewer, db)


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
