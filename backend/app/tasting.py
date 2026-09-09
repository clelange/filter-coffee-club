"""Shared tasting calculations; each tasting response has equal weight."""

from collections import Counter, defaultdict
from statistics import mean

from .models import FlavorTag, Rating
from .schemas import FlavorAxisSummary, RatingAggregate

RATING_FIELDS = ("liking", "acidity", "bitterness", "sweetness", "body")
MIN_RANKING_RATINGS = 3


def ranked_brew_ids(ratings: list[Rating]) -> list[int]:
    """Rank observed brews by exact mean, then response count, then newest ID."""
    scores: dict[int, list[int]] = defaultdict(list)
    for rating in ratings:
        scores[rating.brew_id].append(rating.liking)
    return sorted(
        (brew_id for brew_id, values in scores.items() if len(values) >= MIN_RANKING_RATINGS),
        key=lambda brew_id: (-mean(scores[brew_id]), -len(scores[brew_id]), -brew_id),
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
