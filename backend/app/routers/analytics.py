from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..calculations import brew_ratio, overall_throughput
from ..db import session_dependency
from ..grinders import to_reference_setting
from ..models import Brew, Profile, Rating
from ..schemas import (
    AnalyticsCoffeeSummary,
    AnalyticsRatingMetric,
    AnalyticsResponse,
    RatedBrewInsight,
)
from ..security import require_user
from ..tasting import MIN_RANKING_RATINGS, RATING_FIELDS, ranked_brew_ids, rating_aggregate
from ._brew_support import brew_payload
from ._equipment import grinder_definition_payloads
from ._rating_support import load_flavor_tags

router = APIRouter()


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    db: Session = Depends(session_dependency), _viewer: Profile = Depends(require_user)
) -> AnalyticsResponse:
    brews = list(
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
            .where(Brew.status == "completed")
            .order_by(Brew.completed_at)
        )
    )
    all_ratings = [rating for brew in brews for rating in brew.ratings]
    coffee_brews: dict[int, list[Brew]] = defaultdict(list)
    coffee_names: dict[int, str] = {}
    flavor_tags = load_flavor_tags(db)
    for brew in brews:
        coffee_names[brew.coffee_id] = f"{brew.coffee.roaster} · {brew.coffee.name}"
        coffee_brews[brew.coffee_id].append(brew)
    coffee_summaries = []
    for coffee_id, observations in coffee_brews.items():
        ratings = [rating for brew in observations for rating in brew.ratings]
        if not ratings:
            continue
        coffee = observations[0].coffee
        ranked_ids = ranked_brew_ids(ratings)
        best = next(
            (brew for brew in observations if ranked_ids and brew.id == ranked_ids[0]), None
        )
        coffee_summaries.append(
            AnalyticsCoffeeSummary(
                coffee_id=coffee_id,
                name=coffee_names[coffee_id],
                average=rating_aggregate(ratings, []).averages["liking"],
                ratings=len(ratings),
                brews=sum(bool(brew.ratings) for brew in observations),
                tasters=len({rating.profile_id for rating in ratings}),
                bag_label=f"Bag #{coffee_id}"
                + (f" · roasted {coffee.roast_date.isoformat()}" if coffee.roast_date else ""),
                chart_color=coffee.chart_color,
                available=coffee.available,
                best_brew=(
                    RatedBrewInsight(
                        brew=brew_payload(best),
                        aggregate=rating_aggregate(best.ratings, flavor_tags),
                    )
                    if best
                    else None
                ),
            )
        )
    # Sort on the unrounded pooled score; rounding is for display only.
    coffee_summaries.sort(
        key=lambda item: (
            -mean(
                rating.liking for brew in coffee_brews[item.coffee_id] for rating in brew.ratings
            ),
            -item.ratings,
            item.coffee_id,
        )
    )
    top_coffees = [item for item in coffee_summaries if item.ratings >= MIN_RANKING_RATINGS]
    brews_by_id = {brew.id: brew for brew in brews}
    top_recipes = []
    for brew_id in ranked_brew_ids(all_ratings)[:10]:
        brew = brews_by_id[brew_id]
        top_recipes.append(
            {
                "brew_id": brew.id,
                "name": f"{coffee_names[brew.coffee_id]} · Bag #{brew.coffee_id}",
                "recipe": (
                    f"1:{brew_ratio(brew.water_g, brew.dose_g)} · {brew.temperature_c:g} °C · "
                    f"{brew.grinder.manufacturer} {brew.grinder.model} "
                    f"{brew.grinder_setting:g} {brew.grinder.setting_unit}"
                ),
                "average": rating_aggregate(brew.ratings, []).averages["liking"],
                "ratings": len(brew.ratings),
            }
        )
    flavor_counts = Counter(tag.name for rating in all_ratings for tag in rating.flavor_tags)
    operator_counts: Counter[int] = Counter(
        operator.id for brew in brews for operator in brew.operators
    )
    operators_by_id = {
        operator.id: operator.display_name for brew in brews for operator in brew.operators
    }
    scatter = []
    for brew in brews:
        if not brew.ratings:
            continue
        rating_metrics = {
            field: AnalyticsRatingMetric(
                average=round(mean(getattr(rating, field) for rating in brew.ratings), 2),
                minimum=min(getattr(rating, field) for rating in brew.ratings),
                maximum=max(getattr(rating, field) for rating in brew.ratings),
            )
            for field in RATING_FIELDS
        }
        scatter.append(
            {
                "brew_id": brew.id,
                "coffee_id": brew.coffee_id,
                "coffee": coffee_names[brew.coffee_id],
                "coffee_color": brew.coffee.chart_color,
                "liking": round(mean(rating.liking for rating in brew.ratings), 2),
                "ratings": len(brew.ratings),
                "rating_metrics": rating_metrics,
                "ratio": brew_ratio(brew.water_g, brew.dose_g),
                "temperature_c": brew.temperature_c,
                "grinder_id": brew.grinder_id,
                "grinder_name": f"{brew.grinder.manufacturer} {brew.grinder.model}",
                "grinder_unit": brew.grinder.setting_unit,
                "grinder_setting": brew.grinder_setting,
                "grinder_definition_key": brew.grinder.definition_key,
                "reference_grinder_setting": to_reference_setting(
                    brew.grinder_setting, brew.grinder.definition_key
                ),
                "total_brew_time_s": brew.total_brew_time_s,
                "target_flow_g_s": brew.target_flow_g_s,
                "overall_throughput_g_s": overall_throughput(brew.water_g, brew.total_brew_time_s),
            }
        )
    return AnalyticsResponse(
        counts={"brews": len(brews), "ratings": len(all_ratings), "coffees": len(coffee_brews)},
        top_coffees=top_coffees[:10],
        top_recipes=top_recipes[:10],
        flavor_counts=dict(flavor_counts.most_common(12)),
        operator_counts=[
            {
                "profile_id": profile_id,
                "display_name": operators_by_id[profile_id],
                "brew_count": brew_count,
            }
            for profile_id, brew_count in operator_counts.most_common()
        ],
        scatter=scatter,
        grinder_definitions=grinder_definition_payloads(),
        coffee_summaries=coffee_summaries,
        ranking_min_ratings=MIN_RANKING_RATINGS,
    )
