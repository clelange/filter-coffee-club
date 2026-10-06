from __future__ import annotations

from collections import Counter
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Brew, FlavorTag, Profile, Rating
from ..schemas.ratings import ProfileRatingResult, RatingComparison, RatingItem, RatingSummary
from ..tasting import RATING_FIELDS, rating_aggregate
from ._brew_support import brew_payload


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
