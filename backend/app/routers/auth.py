from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import session_dependency
from ..demo import enforce_demo_write_rate_limit, is_protected_demo_profile, prune_demo_sessions
from ..models import AppSettings, LoginSession, Profile
from ..schemas.profiles import (
    BootstrapInput,
    LoginInput,
    PinChange,
    ProfileIdentity,
    ProfilePublic,
    SessionResponse,
)
from ..security import (
    clear_login_failures,
    create_login_session,
    hash_pin,
    login_attempt_guard,
    login_retry_after,
    record_login_failure,
    require_csrf_token,
    require_login_session,
    verify_pin,
    verify_profile_pin,
)

router = APIRouter()

auth_logger = logging.getLogger("fcc.auth")


def session_payload(login_session: LoginSession) -> SessionResponse:
    return SessionResponse(
        profile=ProfilePublic.model_validate(login_session.profile),
        csrf_token=login_session.csrf_token,
        device_mode=login_session.device_mode,
        expires_at=login_session.expires_at,
    )


def set_session_cookie(request: Request, response: Response, raw: str, hours: int) -> None:
    response.set_cookie(
        request.app.state.settings.session_cookie,
        raw,
        max_age=hours * 3600,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def reserve_bootstrap(db: Session) -> None:
    """Serialize the final first-run check with other bootstrap requests."""

    reserved_id = db.scalar(
        update(AppSettings)
        .where(AppSettings.id == 1)
        .values(active_brew_count=AppSettings.active_brew_count)
        .returning(AppSettings.id)
        .execution_options(synchronize_session=False)
    )
    if reserved_id is None:
        raise RuntimeError("Application settings are missing during first-run setup")
    if (db.scalar(select(func.count(Profile.id))) or 0) > 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Initial setup is already complete")


@router.get("/auth/bootstrap-status")
def bootstrap_status(
    request: Request, db: Session = Depends(session_dependency)
) -> dict[str, bool]:
    if request.app.state.settings.demo_mode:
        return {"required": False}
    return {"required": (db.scalar(select(func.count(Profile.id))) or 0) == 0}


@router.post("/auth/bootstrap", response_model=SessionResponse)
def bootstrap(
    payload: BootstrapInput,
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
) -> SessionResponse:
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="First-run setup is disabled in demo mode")
    if (db.scalar(select(func.count(Profile.id))) or 0) > 0:
        raise HTTPException(status_code=409, detail="Initial setup is already complete")
    pin_hash = hash_pin(payload.pin)
    reserve_bootstrap(db)
    profile = Profile(
        display_name=payload.display_name.strip(),
        pin_hash=pin_hash,
        role="admin",
        pin_change_required=False,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    hours = (
        request.app.state.settings.personal_session_hours
        if payload.device_mode == "personal"
        else request.app.state.settings.kiosk_session_hours
    )
    raw, login_session = create_login_session(db, profile, payload.device_mode, hours)
    set_session_cookie(request, response, raw, hours)
    return session_payload(login_session)


@router.get("/auth/profiles", response_model=list[ProfileIdentity])
def list_public_profiles(db: Session = Depends(session_dependency)) -> list[Profile]:
    return list(
        db.scalars(select(Profile).where(Profile.active.is_(True)).order_by(Profile.display_name))
    )


@router.post(
    "/auth/login",
    response_model=SessionResponse,
    responses={
        429: {
            "description": "Login temporarily blocked after repeated failures",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until another login attempt is allowed",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
) -> SessionResponse:
    enforce_demo_write_rate_limit(request)
    profile = db.get(Profile, payload.profile_id)
    with login_attempt_guard(profile.id if profile is not None else None):
        if profile is not None:
            db.rollback()
            profile = db.get(Profile, payload.profile_id)
        throttle_exempt = bool(
            profile and request.app.state.settings.demo_mode and is_protected_demo_profile(profile)
        )
        retry_after = (
            0
            if profile is None or not profile.active or throttle_exempt
            else login_retry_after(profile)
        )
        if retry_after:
            auth_logger.warning(
                "login_backoff",
                extra={
                    "fields": {
                        "profile_id": payload.profile_id,
                        "failure_count": profile.failed_login_attempts,
                        "retry_after_seconds": retry_after,
                    }
                },
            )
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        if not verify_profile_pin(profile, payload.pin):
            attempts = 0
            delay = 0
            if profile is not None and profile.active and not throttle_exempt:
                attempts, delay = record_login_failure(db, profile)
            auth_logger.warning(
                "login_failure",
                extra={
                    "fields": {
                        "profile_id": payload.profile_id,
                        "failure_count": attempts or None,
                        "retry_after_seconds": delay,
                    }
                },
            )
            if delay:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Try again shortly.",
                    headers={"Retry-After": str(delay)},
                )
            raise HTTPException(status_code=401, detail="Invalid profile or PIN")
        assert profile is not None
        clear_login_failures(profile)
        prune_demo_sessions(request, db)
        hours = (
            request.app.state.settings.personal_session_hours
            if payload.device_mode == "personal"
            else request.app.state.settings.kiosk_session_hours
        )
        raw, login_session = create_login_session(db, profile, payload.device_mode, hours)
        set_session_cookie(request, response, raw, hours)
        return session_payload(login_session)


@router.get("/auth/me", response_model=SessionResponse)
def me(login_session: LoginSession = Depends(require_login_session)) -> SessionResponse:
    return session_payload(login_session)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf_token),
) -> None:
    db.delete(login_session)
    db.commit()
    response.delete_cookie(request.app.state.settings.session_cookie, path="/")


@router.post("/auth/pin", status_code=204)
def change_pin(
    payload: PinChange,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf_token),
) -> None:
    profile = login_session.profile
    if request.app.state.settings.demo_mode and is_protected_demo_profile(profile):
        raise HTTPException(status_code=403, detail="Demo profile credentials are fixed")
    if not verify_pin(profile.pin_hash, payload.current_pin):
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")
    if verify_pin(profile.pin_hash, payload.new_pin):
        raise HTTPException(
            status_code=400, detail="New PIN must be different from the current PIN"
        )
    profile.pin_hash = hash_pin(payload.new_pin)
    profile.pin_change_required = False
    clear_login_failures(profile)
    db.commit()
