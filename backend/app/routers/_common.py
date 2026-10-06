from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AppSettings


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def effective_public_url(request: Request, db: Session) -> str:
    row = get_settings(db)
    stored_url = None if request.app.state.settings.demo_mode else row.public_base_url
    configured = (stored_url or request.app.state.settings.public_base_url or "").strip()
    return configured.rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"
