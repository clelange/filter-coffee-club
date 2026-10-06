from __future__ import annotations

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.orm import Session

from ..branding import replace_logo_path, store_logo
from ..db import session_dependency
from ..demo import DEMO_NOTICE, DEMO_PIN, DEMO_PROFILE_NAMES
from ..models import DEFAULT_BREWING_LOGO_PATH, LoginSession
from ..schemas import AppSettingsResponse, AppSettingsUpdate
from ..security import require_csrf
from ._branding import branding_http_errors, require_branding_admin
from ._common import effective_public_url, get_settings

router = APIRouter()


@router.get("/settings", response_model=AppSettingsResponse)
def public_settings(
    request: Request, db: Session = Depends(session_dependency)
) -> AppSettingsResponse:
    item = get_settings(db)
    result = AppSettingsResponse.model_validate(item)
    result.app_version = request.app.state.settings.deployed_version
    url = effective_public_url(request, db)
    result.public_base_url = url
    result.public_url_needs_configuration = url in {
        "http://filter-coffee-club.local",
        "http://localhost:8000",
    }
    if request.app.state.settings.demo_mode:
        result.demo_mode = True
        result.demo_notice = DEMO_NOTICE
        result.demo_pin = DEMO_PIN
        result.demo_profile_names = list(DEMO_PROFILE_NAMES)
    return result


@router.put("/settings", response_model=AppSettingsResponse)
def update_settings(
    payload: AppSettingsUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    require_branding_admin(request, login_session)
    item = get_settings(db)
    for key, value in payload.model_dump().items():
        setattr(item, key, value.rstrip("/") if key == "public_base_url" and value else value)
    db.commit()
    return public_settings(request, db)


@router.post("/settings/logo", response_model=AppSettingsResponse)
async def upload_logo(
    logo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    require_branding_admin(request, login_session)
    item = get_settings(db)
    settings = request.app.state.settings
    content = await logo.read(settings.max_logo_bytes + 1)
    with branding_http_errors():
        logo_path = await store_logo(content, logo.content_type, settings, "logo")
    replace_logo_path(
        db,
        settings,
        item,
        "logo_path",
        logo_path,
        created_upload=logo_path,
    )
    return public_settings(request, db)


@router.post("/settings/brewing-logo", response_model=AppSettingsResponse)
async def upload_brewing_logo(
    logo: UploadFile,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    require_branding_admin(request, login_session)
    item = get_settings(db)
    settings = request.app.state.settings
    content = await logo.read(settings.max_logo_bytes + 1)
    with branding_http_errors():
        logo_path = await store_logo(content, logo.content_type, settings, "brewing-logo")
    replace_logo_path(
        db,
        settings,
        item,
        "brewing_logo_path",
        logo_path,
        created_upload=logo_path,
    )
    return public_settings(request, db)


@router.delete("/settings/brewing-logo", response_model=AppSettingsResponse)
def clear_brewing_logo(
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    require_branding_admin(request, login_session)
    item = get_settings(db)
    replace_logo_path(db, request.app.state.settings, item, "brewing_logo_path", None)
    return public_settings(request, db)


@router.post("/settings/brewing-logo/default", response_model=AppSettingsResponse)
def restore_default_brewing_logo(
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> AppSettingsResponse:
    require_branding_admin(request, login_session)
    item = get_settings(db)
    replace_logo_path(
        db,
        request.app.state.settings,
        item,
        "brewing_logo_path",
        DEFAULT_BREWING_LOGO_PATH,
    )
    return public_settings(request, db)
