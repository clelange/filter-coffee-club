from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .brews import BrewResponse
from .profiles import ProfileIdentity


class RatingInput(BaseModel):
    liking: int = Field(ge=1, le=9)
    acidity: int = Field(ge=0, le=5)
    bitterness: int = Field(ge=0, le=5)
    sweetness: int = Field(ge=0, le=5)
    body: int = Field(ge=0, le=5)
    flavor_tag_ids: list[int] = Field(default_factory=list, max_length=5)

    @field_validator("flavor_tag_ids")
    @classmethod
    def unique_tags(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Flavor tags must be unique")
        return value


class RatingItem(RatingInput):
    profile_id: int
    profile_name: str
    updated_at: datetime


class FlavorAxisSummary(BaseModel):
    id: int
    label: str
    mentions: int
    total: int


class RatingAggregate(BaseModel):
    count: int = 0
    averages: dict[str, float] = Field(default_factory=dict)
    flavor_axes: list[FlavorAxisSummary] = Field(default_factory=list)


class RatedBrewInsight(BaseModel):
    brew: BrewResponse
    aggregate: RatingAggregate


class CoffeeRatingInsights(BaseModel):
    coffee_id: int
    aggregate: RatingAggregate
    rated_brew_count: int
    rated_brews: list[RatedBrewInsight] = Field(default_factory=list)
    next_offset: int | None = None
    taster_count: int = 0
    best_brew: RatedBrewInsight | None = None
    ranking_min_ratings: int = 3


class RatingSummary(BaseModel):
    can_view: bool
    own_rating: RatingItem | None
    ratings: list[RatingItem] = Field(default_factory=list)
    count: int = 0
    averages: dict[str, float] = Field(default_factory=dict)
    flavor_counts: dict[str, int] = Field(default_factory=dict)
    flavor_axes: list[FlavorAxisSummary] = Field(default_factory=list)


class ProfileCoffeePreference(BaseModel):
    coffee_id: int
    coffee_name: str
    coffee_roaster: str
    rating_count: int
    average_liking: float


class RatingComparison(BaseModel):
    brew_id: int
    rating: RatingItem
    total_rating_count: int
    peer_count: int
    peer_averages: dict[str, float] = Field(default_factory=dict)
    peer_deltas: dict[str, float] = Field(default_factory=dict)
    selected_flavors: list[str] = Field(default_factory=list)
    peer_flavor_counts: dict[str, int] = Field(default_factory=dict)


class ProfileRatingResult(RatingComparison):
    brew: BrewResponse


class ProfileRatingsResponse(BaseModel):
    profile: ProfileIdentity
    is_self: bool
    is_complete_history: bool
    rating_count: int
    averages: dict[str, float] = Field(default_factory=dict)
    favorite_coffees: list[ProfileCoffeePreference] = Field(default_factory=list)
    ratings: list[ProfileRatingResult] = Field(default_factory=list)
    next_offset: int | None = None


class RatingLinkResponse(BaseModel):
    active: bool
    brew: BrewResponse | None
