from __future__ import annotations

import hashlib
import math
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import case, or_, select, update
from sqlalchemy.orm import Session

from .db import session_dependency, utcnow
from .demo import enforce_demo_write_rate_limit
from .models import LoginSession, Profile

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
dummy_pin_hash = password_hasher.hash(secrets.token_urlsafe(32))

LOGIN_BACKOFF_THRESHOLD = 3
LOGIN_BACKOFF_BASE_SECONDS = 30
LOGIN_BACKOFF_MAX_SECONDS = 15 * 60
LOGIN_FAILURE_RESET_WINDOW = timedelta(hours=24)
_login_locks: dict[int, Lock] = {}
_login_locks_guard = Lock()


def hash_pin(pin: str) -> str:
    return password_hasher.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    try:
        return password_hasher.verify(pin_hash, pin)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


@contextmanager
def login_attempt_guard(profile_id: int | None) -> Iterator[None]:
    if profile_id is None:
        yield
        return
    with _login_locks_guard:
        lock = _login_locks.setdefault(profile_id, Lock())
    with lock:
        yield


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def login_retry_after(profile: Profile, now: datetime | None = None) -> int:
    if profile.login_blocked_until is None:
        return 0
    current = now or utcnow()
    remaining = (_as_aware(profile.login_blocked_until) - current).total_seconds()
    return max(0, math.ceil(remaining))


def record_login_failure(
    db: Session, profile: Profile, now: datetime | None = None
) -> tuple[int, int]:
    current = now or utcnow()
    reset_before = current - LOGIN_FAILURE_RESET_WINDOW
    new_attempts = case(
        (
            or_(
                Profile.last_failed_login_at.is_(None),
                Profile.last_failed_login_at <= reset_before,
            ),
            1,
        ),
        else_=Profile.failed_login_attempts + 1,
    )
    attempts = db.scalar(
        update(Profile)
        .where(Profile.id == profile.id)
        .values(
            failed_login_attempts=new_attempts,
            last_failed_login_at=current,
        )
        .returning(Profile.failed_login_attempts)
    )
    if attempts is None:
        raise RuntimeError("Profile disappeared while recording a login failure")

    delay = 0
    if attempts >= LOGIN_BACKOFF_THRESHOLD:
        delay = min(
            LOGIN_BACKOFF_BASE_SECONDS * 2 ** (attempts - LOGIN_BACKOFF_THRESHOLD),
            LOGIN_BACKOFF_MAX_SECONDS,
        )
    db.execute(
        update(Profile)
        .where(Profile.id == profile.id)
        .values(login_blocked_until=current + timedelta(seconds=delay) if delay else None)
    )
    db.commit()
    db.refresh(profile)
    return attempts, delay


def clear_login_failures(profile: Profile) -> None:
    profile.failed_login_attempts = 0
    profile.last_failed_login_at = None
    profile.login_blocked_until = None


def verify_profile_pin(profile: Profile | None, pin: str) -> bool:
    pin_hash = profile.pin_hash if profile is not None and profile.active else dummy_pin_hash
    verified = verify_pin(pin_hash, pin)
    return verified and profile is not None and profile.active


def create_login_session(
    db: Session, profile: Profile, device_mode: str, duration_hours: int
) -> tuple[str, LoginSession]:
    raw_token = secrets.token_urlsafe(32)
    login_session = LoginSession(
        token_hash=token_hash(raw_token),
        csrf_token=secrets.token_urlsafe(24),
        profile_id=profile.id,
        device_mode=device_mode,
        expires_at=utcnow() + timedelta(hours=duration_hours),
    )
    db.add(login_session)
    db.commit()
    db.refresh(login_session)
    login_session.profile = profile
    return raw_token, login_session


def optional_login_session(
    request: Request, db: Session = Depends(session_dependency)
) -> LoginSession | None:
    raw = request.cookies.get(request.app.state.settings.session_cookie)
    if not raw:
        return None
    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == token_hash(raw))
    )
    if login_session is None or _as_aware(login_session.expires_at) <= utcnow():
        if login_session is not None:
            db.delete(login_session)
            db.commit()
        return None
    if not login_session.profile.active:
        return None
    return login_session


def require_login_session(
    login_session: LoginSession | None = Depends(optional_login_session),
) -> LoginSession:
    if login_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return login_session


def require_pin_change_complete(login_session: LoginSession) -> LoginSession:
    if login_session.profile.pin_change_required:
        raise HTTPException(status_code=403, detail="PIN change required")
    return login_session


def require_user(login_session: LoginSession = Depends(require_login_session)) -> Profile:
    require_pin_change_complete(login_session)
    return login_session.profile


def require_admin(profile: Profile = Depends(require_user)) -> Profile:
    if profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return profile


def require_csrf_token(
    request: Request,
    login_session: LoginSession = Depends(require_login_session),
) -> LoginSession:
    supplied = request.headers.get("X-CSRF-Token")
    if not supplied or not secrets.compare_digest(supplied, login_session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    origin = request.headers.get("Origin")
    if origin:
        configured = {
            item.strip().rstrip("/")
            for item in request.app.state.settings.allowed_origins.split(",")
            if item.strip()
        }
        host_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
        if (
            configured
            and origin.rstrip("/") not in configured
            and origin.rstrip("/") != host_origin
        ):
            raise HTTPException(status_code=403, detail="Untrusted request origin")
    enforce_demo_write_rate_limit(request)
    return login_session


def require_csrf(
    login_session: LoginSession = Depends(require_csrf_token),
) -> LoginSession:
    return require_pin_change_complete(login_session)


def require_personal_csrf(
    login_session: LoginSession = Depends(require_csrf),
) -> LoginSession:
    if login_session.device_mode != "personal":
        raise HTTPException(status_code=403, detail="Photo changes are unavailable in kiosk mode")
    return login_session
