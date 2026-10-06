from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, Request

from ..branding import LogoTooLargeError, UnsupportedLogoError
from ..models import LoginSession


@contextmanager
def branding_http_errors() -> Iterator[None]:
    try:
        yield
    except LogoTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedLogoError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


def require_branding_admin(request: Request, login_session: LoginSession) -> None:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    if request.app.state.settings.demo_mode:
        raise HTTPException(status_code=403, detail="Branding is read-only in demo mode")
