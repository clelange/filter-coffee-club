from __future__ import annotations

from sqlalchemy.orm import Session

from ..calculations import (
    brew_ratio,
    overall_throughput,
)
from ..models import Brew
from ..schemas.brews import BrewActivityItem, BrewResponse
from ..schemas.profiles import ProfileIdentity
from ..services.brew_store import load_brew as query_brew
from ._brew_errors import brew_http_errors


def brew_payload(brew: Brew, include_token: bool = False) -> BrewResponse:
    ratio = brew_ratio(brew.water_g, brew.dose_g)
    throughput = overall_throughput(brew.water_g, brew.total_brew_time_s)
    return BrewResponse(
        id=brew.id,
        coffee_id=brew.coffee_id,
        operator_id=brew.operator_id,
        operators=[
            ProfileIdentity.model_validate(operator)
            for operator in sorted(
                brew.operators,
                key=lambda operator: (
                    operator.id != brew.operator_id,
                    operator.display_name.casefold(),
                ),
            )
        ],
        revision=brew.revision,
        grinder_id=brew.grinder_id,
        dripper_id=brew.dripper_id,
        filter_id=brew.filter_id,
        source_preset_id=brew.source_preset_id,
        cloned_from_id=brew.cloned_from_id,
        dose_g=brew.dose_g,
        water_g=brew.water_g,
        target_ratio=brew.target_ratio,
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


def brew_activity_payload(brew: Brew, include_token: bool = False) -> BrewActivityItem:
    return BrewActivityItem(
        id=brew.id,
        coffee_name=brew.coffee.name,
        coffee_roaster=brew.coffee.roaster,
        operators=[
            ProfileIdentity.model_validate(operator)
            for operator in sorted(
                brew.operators,
                key=lambda operator: (
                    operator.id != brew.operator_id,
                    operator.display_name.casefold(),
                ),
            )
        ],
        status=brew.status,
        rating_token=brew.rating_token if include_token else None,
    )


def load_brew(db: Session, brew_id: int) -> Brew:
    with brew_http_errors():
        return query_brew(db, brew_id)
