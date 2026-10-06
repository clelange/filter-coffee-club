from __future__ import annotations

from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..calculations import brew_ratio, overall_throughput
from ..db import session_dependency
from ..models import Brew, BrewFilter, Coffee, Dripper, Grinder, LoginSession
from ..schemas.catalog import (
    CatalogBrewResult,
    CatalogInsights,
    CatalogKind,
    CatalogUsageItem,
    CatalogUsageResponse,
)
from ..security import optional_login_session
from ._brew_support import brew_payload

router = APIRouter()


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
