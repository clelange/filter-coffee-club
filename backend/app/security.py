from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import session_dependency, utcnow
from .models import LoginSession, Profile

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def hash_pin(pin: str) -> str:
    return password_hasher.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    try:
        return password_hasher.verify(pin_hash, pin)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def enforce_login_rate_limit(key: str) -> None:
    now = datetime.now(UTC)
    window = now - timedelta(minutes=5)
    attempts = _attempts[key]
    while attempts and attempts[0] < window:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again shortly.")


def record_login_failure(key: str) -> None:
    _attempts[key].append(datetime.now(UTC))


def clear_login_failures(key: str) -> None:
    _attempts.pop(key, None)


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


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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


def require_user(login_session: LoginSession = Depends(require_login_session)) -> Profile:
    return login_session.profile


def require_admin(profile: Profile = Depends(require_user)) -> Profile:
    if profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return profile


def require_csrf(
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
    return login_session
