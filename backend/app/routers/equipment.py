from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_dependency
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..grinders import grinder_definition
from ..models import BrewFilter, Dripper, Grinder, LoginSession, PresetGrinderRange, RecipePreset
from ..schemas.equipment import (
    DripperResponse,
    EquipmentInput,
    FilterInput,
    FilterResponse,
    GrinderCreate,
    GrinderDefinitionResponse,
    GrinderInput,
    GrinderResponse,
)
from ..schemas.photos import PhotoFramingUpdate
from ..security import require_csrf, require_login_session, require_personal_csrf
from ._catalog_photos import delete_item_photo, reframe_item_photo, upload_item_photo
from ._equipment import grinder_definition_payloads

router = APIRouter()


@router.get("/grinders", response_model=list[GrinderResponse])
def list_grinders(db: Session = Depends(session_dependency)) -> list[Grinder]:
    return list(
        db.scalars(select(Grinder).where(Grinder.archived.is_(False)).order_by(Grinder.model))
    )


@router.get("/grinder-definitions", response_model=list[GrinderDefinitionResponse])
def list_grinder_definitions() -> list[GrinderDefinitionResponse]:
    return grinder_definition_payloads()


@router.post("/grinders", response_model=GrinderResponse)
def create_grinder(
    payload: GrinderCreate,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Grinder:
    enforce_demo_capacity(request, db, Grinder)
    definition = grinder_definition(payload.definition_key)
    if payload.definition_key == "custom":
        for preset_range in payload.preset_ranges:
            if db.get(RecipePreset, preset_range.preset_id) is None:
                raise HTTPException(status_code=422, detail="Preset not found")
        item = Grinder(
            definition_key="custom",
            manufacturer=payload.manufacturer,
            model=payload.model,
            setting_unit=payload.setting_unit,
            setting_step=payload.setting_step,
            soft_min=payload.soft_min,
            soft_max=payload.soft_max,
            guidance=payload.guidance,
        )
    else:
        assert definition.manufacturer is not None and definition.model is not None
        item = Grinder(
            definition_key=definition.key,
            manufacturer=definition.manufacturer,
            model=definition.model,
            setting_unit=definition.setting_unit,
            setting_step=definition.setting_step,
            soft_min=definition.soft_min,
            soft_max=definition.soft_max,
            guidance=definition.guidance,
        )
    db.add(item)
    db.flush()
    if payload.definition_key == "custom":
        db.add_all(
            PresetGrinderRange(
                preset_id=preset_range.preset_id,
                grinder_id=item.id,
                setting_min=preset_range.setting_min,
                setting_max=preset_range.setting_max,
            )
            for preset_range in payload.preset_ranges
            if preset_range.setting_min is not None and preset_range.setting_max is not None
        )
    db.commit()
    db.refresh(item)
    return item


@router.get("/grinders/{item_id}", response_model=GrinderResponse)
def get_grinder(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> Grinder:
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    return item


@router.put("/grinders/{item_id}", response_model=GrinderResponse)
def update_grinder(
    item_id: int,
    payload: GrinderInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Grinder:
    enforce_demo_seed_protection(request, Grinder, item_id)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    if item.definition_key != "custom":
        raise HTTPException(status_code=422, detail="Predefined grinder details cannot be edited")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/grinders/{item_id}/photo", response_model=GrinderResponse)
async def put_grinder_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    focus_x: float | None = Form(default=None, ge=0, le=1),
    focus_y: float | None = Form(default=None, ge=0, le=1),
    zoom: float | None = Form(default=None, ge=1, le=3),
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Grinder:
    return await upload_item_photo(request, db, Grinder, item_id, photo, focus_x, focus_y, zoom)


@router.patch("/grinders/{item_id}/photo", response_model=GrinderResponse)
def patch_grinder_photo_framing(
    item_id: int,
    payload: PhotoFramingUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Grinder:
    return reframe_item_photo(request, db, Grinder, item_id, payload.photo_framing)


@router.delete("/grinders/{item_id}/photo", response_model=GrinderResponse)
def delete_grinder_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Grinder:
    return delete_item_photo(request, db, Grinder, item_id)


@router.post("/grinders/{item_id}/archive", response_model=GrinderResponse)
def archive_grinder(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Grinder:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, Grinder, item_id)
    item = db.get(Grinder, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grinder not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item


@router.get("/drippers", response_model=list[DripperResponse])
def list_drippers(db: Session = Depends(session_dependency)) -> list[Dripper]:
    return list(
        db.scalars(select(Dripper).where(Dripper.archived.is_(False)).order_by(Dripper.model))
    )


@router.post("/drippers", response_model=DripperResponse)
def create_dripper(
    payload: EquipmentInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Dripper:
    enforce_demo_capacity(request, db, Dripper)
    item = Dripper(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/drippers/{item_id}", response_model=DripperResponse)
def get_dripper(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> Dripper:
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    return item


@router.put("/drippers/{item_id}", response_model=DripperResponse)
def update_dripper(
    item_id: int,
    payload: EquipmentInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> Dripper:
    enforce_demo_seed_protection(request, Dripper, item_id)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/drippers/{item_id}/photo", response_model=DripperResponse)
async def put_dripper_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    focus_x: float | None = Form(default=None, ge=0, le=1),
    focus_y: float | None = Form(default=None, ge=0, le=1),
    zoom: float | None = Form(default=None, ge=1, le=3),
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Dripper:
    return await upload_item_photo(request, db, Dripper, item_id, photo, focus_x, focus_y, zoom)


@router.patch("/drippers/{item_id}/photo", response_model=DripperResponse)
def patch_dripper_photo_framing(
    item_id: int,
    payload: PhotoFramingUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Dripper:
    return reframe_item_photo(request, db, Dripper, item_id, payload.photo_framing)


@router.delete("/drippers/{item_id}/photo", response_model=DripperResponse)
def delete_dripper_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> Dripper:
    return delete_item_photo(request, db, Dripper, item_id)


@router.post("/drippers/{item_id}/archive", response_model=DripperResponse)
def archive_dripper(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> Dripper:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, Dripper, item_id)
    item = db.get(Dripper, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dripper not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item


@router.get("/filters", response_model=list[FilterResponse])
def list_filters(db: Session = Depends(session_dependency)) -> list[BrewFilter]:
    return list(
        db.scalars(
            select(BrewFilter).where(BrewFilter.archived.is_(False)).order_by(BrewFilter.name)
        )
    )


@router.post("/filters", response_model=FilterResponse)
def create_filter(
    payload: FilterInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    enforce_demo_capacity(request, db, BrewFilter)
    item = BrewFilter(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/filters/{item_id}", response_model=FilterResponse)
def get_filter(
    item_id: int,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_login_session),
) -> BrewFilter:
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    return item


@router.put("/filters/{item_id}", response_model=FilterResponse)
def update_filter(
    item_id: int,
    payload: FilterInput,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    enforce_demo_seed_protection(request, BrewFilter, item_id)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.put("/filters/{item_id}/photo", response_model=FilterResponse)
async def put_filter_photo(
    item_id: int,
    photo: UploadFile,
    request: Request,
    focus_x: float | None = Form(default=None, ge=0, le=1),
    focus_y: float | None = Form(default=None, ge=0, le=1),
    zoom: float | None = Form(default=None, ge=1, le=3),
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> BrewFilter:
    return await upload_item_photo(request, db, BrewFilter, item_id, photo, focus_x, focus_y, zoom)


@router.patch("/filters/{item_id}/photo", response_model=FilterResponse)
def patch_filter_photo_framing(
    item_id: int,
    payload: PhotoFramingUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> BrewFilter:
    return reframe_item_photo(request, db, BrewFilter, item_id, payload.photo_framing)


@router.delete("/filters/{item_id}/photo", response_model=FilterResponse)
def delete_filter_photo(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    _session: LoginSession = Depends(require_personal_csrf),
) -> BrewFilter:
    return delete_item_photo(request, db, BrewFilter, item_id)


@router.post("/filters/{item_id}/archive", response_model=FilterResponse)
def archive_filter(
    item_id: int,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> BrewFilter:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, BrewFilter, item_id)
    item = db.get(BrewFilter, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    item.archived = True
    db.commit()
    db.refresh(item)
    return item
