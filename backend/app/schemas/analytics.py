from __future__ import annotations

from pydantic import BaseModel, Field

from .equipment import GrinderDefinitionKey, GrinderDefinitionResponse
from .ratings import RatedBrewInsight


class AnalyticsCounts(BaseModel):
    brews: int
    ratings: int
    coffees: int


class AnalyticsCoffeeRank(BaseModel):
    coffee_id: int
    name: str
    average: float
    ratings: int
    brews: int = 0
    tasters: int = 0
    bag_label: str = ""


class AnalyticsCoffeeSummary(AnalyticsCoffeeRank):
    chart_color: str
    available: bool
    best_brew: RatedBrewInsight | None = None


class AnalyticsRecipeRank(BaseModel):
    brew_id: int
    name: str
    recipe: str
    average: float
    ratings: int


class AnalyticsOperatorCount(BaseModel):
    profile_id: int
    display_name: str
    brew_count: int


class AnalyticsRatingMetric(BaseModel):
    average: float
    minimum: int
    maximum: int


class AnalyticsRatingMetrics(BaseModel):
    liking: AnalyticsRatingMetric
    acidity: AnalyticsRatingMetric
    bitterness: AnalyticsRatingMetric
    sweetness: AnalyticsRatingMetric
    body: AnalyticsRatingMetric


class AnalyticsPoint(BaseModel):
    brew_id: int
    coffee_id: int
    coffee: str
    coffee_color: str
    liking: float
    ratings: int
    rating_metrics: AnalyticsRatingMetrics
    ratio: float
    temperature_c: float
    grinder_id: int
    grinder_name: str
    grinder_unit: str
    grinder_setting: float
    grinder_definition_key: GrinderDefinitionKey
    reference_grinder_setting: float | None
    total_brew_time_s: int | None
    target_flow_g_s: float | None
    overall_throughput_g_s: float | None


class AnalyticsResponse(BaseModel):
    counts: AnalyticsCounts
    top_coffees: list[AnalyticsCoffeeRank]
    top_recipes: list[AnalyticsRecipeRank]
    flavor_counts: dict[str, int]
    operator_counts: list[AnalyticsOperatorCount]
    scatter: list[AnalyticsPoint]
    grinder_definitions: list[GrinderDefinitionResponse] = Field(default_factory=list)
    coffee_summaries: list[AnalyticsCoffeeSummary] = Field(default_factory=list)
    ranking_min_ratings: int = 3
