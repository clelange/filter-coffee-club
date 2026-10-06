from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import session_dependency
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..models import Grinder, LoginSession, PresetGrinderRange, RecipePreset
from ..schemas.presets import PresetResponse, PresetUpdate
from ..security import require_csrf
from ._equipment import active_grinders, preset_payload, validate_preset_grinder_ranges

router = APIRouter()


@router.get("/presets", response_model=list[PresetResponse])
def list_presets(
    active_only: bool = True, db: Session = Depends(session_dependency)
) -> list[PresetResponse]:
    query = (
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .order_by(RecipePreset.sort_order)
    )
    if active_only:
        query = query.where(RecipePreset.active.is_(True))
    grinders = active_grinders(db)
    return [preset_payload(item, grinders) for item in db.scalars(query)]


@router.put("/presets/{preset_id}", response_model=PresetResponse)
def update_preset(
    preset_id: int,
    payload: PresetUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> PresetResponse:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, RecipePreset, preset_id)
    item = db.get(RecipePreset, preset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    validate_preset_grinder_ranges(db, payload)
    for key, value in payload.model_dump(
        exclude={"reference_grinder_range", "custom_grinder_ranges"}
    ).items():
        setattr(item, key, value)
    reference_range = payload.reference_grinder_range
    item.reference_setting_min = reference_range.setting_min if reference_range else None
    item.reference_setting_max = reference_range.setting_max if reference_range else None
    custom_grinder_ids = set(
        db.scalars(
            select(Grinder.id).where(
                Grinder.definition_key == "custom", Grinder.archived.is_(False)
            )
        )
    )
    item.grinder_ranges[:] = [
        grinder_range
        for grinder_range in item.grinder_ranges
        if grinder_range.grinder_id not in custom_grinder_ids
    ]
    db.flush()
    for grinder_range in payload.custom_grinder_ranges:
        item.grinder_ranges.append(PresetGrinderRange(**grinder_range.model_dump()))
    db.commit()
    refreshed = db.scalar(
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .where(RecipePreset.id == preset_id)
    )
    assert refreshed is not None
    return preset_payload(refreshed, active_grinders(db))


@router.post("/presets", response_model=PresetResponse)
def create_preset(
    payload: PresetUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> PresetResponse:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_capacity(request, db, RecipePreset)
    validate_preset_grinder_ranges(db, payload)
    reference_range = payload.reference_grinder_range
    item = RecipePreset(
        **payload.model_dump(exclude={"reference_grinder_range", "custom_grinder_ranges"}),
        reference_setting_min=reference_range.setting_min if reference_range else None,
        reference_setting_max=reference_range.setting_max if reference_range else None,
    )
    item.grinder_ranges = [
        PresetGrinderRange(**grinder_range.model_dump())
        for grinder_range in payload.custom_grinder_ranges
    ]
    db.add(item)
    db.commit()
    refreshed = db.scalar(
        select(RecipePreset)
        .options(selectinload(RecipePreset.grinder_ranges))
        .where(RecipePreset.id == item.id)
    )
    assert refreshed is not None
    return preset_payload(refreshed, active_grinders(db))
