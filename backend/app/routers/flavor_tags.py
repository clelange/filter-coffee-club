from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_dependency
from ..demo import enforce_demo_capacity, enforce_demo_seed_protection
from ..models import FlavorTag, LoginSession
from ..schemas.flavor_tags import FlavorTagInput, FlavorTagResponse
from ..security import require_csrf

router = APIRouter()


@router.get("/flavor-tags", response_model=list[FlavorTagResponse])
def list_flavor_tags(
    active_only: bool = True, db: Session = Depends(session_dependency)
) -> list[FlavorTag]:
    query = select(FlavorTag).order_by(FlavorTag.parent_id, FlavorTag.sort_order, FlavorTag.name)
    if active_only:
        query = query.where(FlavorTag.active.is_(True))
    return list(db.scalars(query))


@router.post("/flavor-tags", response_model=FlavorTagResponse)
def create_flavor_tag(
    payload: FlavorTagInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> FlavorTag:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_capacity(request, db, FlavorTag)
    item = FlavorTag(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/flavor-tags/{tag_id}", response_model=FlavorTagResponse)
def update_flavor_tag(
    tag_id: int,
    payload: FlavorTagInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> FlavorTag:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    enforce_demo_seed_protection(request, FlavorTag, tag_id)
    item = db.get(FlavorTag, tag_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Flavor tag not found")
    if payload.parent_id == item.id:
        raise HTTPException(status_code=422, detail="A tag cannot be its own parent")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
