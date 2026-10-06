from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..db import session_dependency, utcnow
from ..mattermost import (
    MattermostClient,
    MattermostError,
    cancel_stale_target_notifications,
    credential_status,
    decrypt_credential,
    encrypt_credential,
    encryption_available,
    get_integration,
    normalize_server_url,
    normalize_webhook_url,
    queue_counts,
    target_fingerprint,
)
from ..models import LoginSession, MattermostNotification, Profile
from ..schemas import (
    MattermostRetryResponse,
    MattermostSettingsResponse,
    MattermostSettingsUpdate,
    MattermostTestResponse,
    MattermostVerifyInput,
    MattermostVerifyResponse,
)
from ..security import require_admin, require_csrf

router = APIRouter()


def mattermost_settings_response(request: Request, db: Session) -> MattermostSettingsResponse:
    item = get_integration(db)
    pending_count, failed_count = queue_counts(db)
    return MattermostSettingsResponse(
        enabled=item.enabled and not request.app.state.settings.demo_mode,
        server_url=item.server_url,
        auth_mode=item.auth_mode,
        credential_configured=item.credential_ciphertext is not None,
        encryption_available=encryption_available(request.app.state.settings),
        credential_status=credential_status(request.app.state.settings, item.credential_ciphertext),
        account_user_id=item.account_user_id,
        account_username=item.account_username,
        team_id=item.team_id,
        team_name=item.team_name,
        channel_id=item.channel_id,
        channel_name=item.channel_name,
        channel_display_name=item.channel_display_name,
        announce_brew_started=item.announce_brew_started,
        mention_channel_on_started=item.mention_channel_on_started,
        announce_ready_to_rate=item.announce_ready_to_rate,
        mention_channel_on_ready=item.mention_channel_on_ready,
        last_tested_at=item.last_tested_at,
        last_delivery_at=item.last_delivery_at,
        last_error_at=item.last_error_at,
        last_error=item.last_error,
        pending_count=pending_count,
        failed_count=failed_count,
    )


def require_mattermost_mutation_admin(request: Request, login_session: LoginSession) -> None:
    if login_session.profile.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    if request.app.state.settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Mattermost integration is disabled in demo mode",
        )


def raise_mattermost_http_error(error: MattermostError) -> None:
    raise HTTPException(status_code=502 if error.retryable else 422, detail=str(error)) from error


@router.get("/settings/mattermost", response_model=MattermostSettingsResponse)
def get_mattermost_settings(
    request: Request,
    db: Session = Depends(session_dependency),
    _admin: Profile = Depends(require_admin),
) -> MattermostSettingsResponse:
    return mattermost_settings_response(request, db)


@router.post("/settings/mattermost/verify", response_model=MattermostVerifyResponse)
def verify_mattermost_pat(
    payload: MattermostVerifyInput,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> MattermostVerifyResponse:
    require_mattermost_mutation_admin(request, login_session)
    item = get_integration(db)
    try:
        server_url = normalize_server_url(payload.server_url)
        if payload.credential is not None:
            credential = payload.credential.get_secret_value()
        else:
            if item.auth_mode != "pat" or normalize_server_url(item.server_url) != server_url:
                raise MattermostError(
                    "Re-enter the personal access token when changing the Mattermost server"
                )
            credential = decrypt_credential(
                request.app.state.settings,
                item.credential_ciphertext,
            )
        return MattermostClient(server_url, credential, "pat").verify_pat()
    except MattermostError as exc:
        raise_mattermost_http_error(exc)


@router.put("/settings/mattermost", response_model=MattermostSettingsResponse)
def update_mattermost_settings(
    payload: MattermostSettingsUpdate,
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> MattermostSettingsResponse:
    require_mattermost_mutation_admin(request, login_session)
    item = get_integration(db)
    new_credential = (
        payload.credential.get_secret_value() if payload.credential is not None else None
    )
    changing_mode = item.auth_mode != payload.auth_mode
    try:
        server_url = normalize_server_url(payload.server_url)
        changing_server = normalize_server_url(item.server_url) != server_url
        if new_credential is not None and not encryption_available(request.app.state.settings):
            raise MattermostError(
                "Mattermost secret encryption is unavailable; configure FCC_MATTERMOST_SECRET_KEY"
            )
        if new_credential is not None:
            credential = new_credential
        elif item.credential_ciphertext is not None and not changing_mode and changing_server:
            raise MattermostError(
                "Re-enter the Mattermost credential when changing the Mattermost server"
            )
        elif item.credential_ciphertext is not None and not changing_mode:
            credential = decrypt_credential(request.app.state.settings, item.credential_ciphertext)
        else:
            credential = None

        verification: MattermostVerifyResponse | None = None
        selected_channel = None
        if payload.auth_mode == "pat" and credential is not None:
            needs_verification = (
                new_credential is not None
                or (payload.enabled and not item.enabled)
                or changing_server
                or item.channel_id != payload.channel_id
            )
            if needs_verification:
                verification = MattermostClient(server_url, credential, "pat").verify_pat()
                if payload.channel_id:
                    selected_channel = next(
                        (
                            channel
                            for channel in verification.channels
                            if channel.channel_id == payload.channel_id
                        ),
                        None,
                    )
                    if selected_channel is None:
                        raise MattermostError(
                            "Selected Mattermost channel is not available to this account"
                        )
        elif payload.auth_mode == "webhook" and credential is not None:
            credential = normalize_webhook_url(credential, server_url)

        if payload.enabled and credential is None:
            raise MattermostError("A Mattermost credential is required before enabling delivery")

        next_fingerprint = (
            target_fingerprint(
                auth_mode=payload.auth_mode,
                server_url=server_url,
                channel_id=payload.channel_id,
                credential=credential,
            )
            if credential is not None
            else None
        )
        destination_changed = item.target_fingerprint != next_fingerprint
        if destination_changed or not payload.enabled:
            cancel_stale_target_notifications(db, next_fingerprint if payload.enabled else None)

        item.enabled = payload.enabled
        item.server_url = server_url
        item.auth_mode = payload.auth_mode
        if new_credential is not None:
            item.credential_ciphertext = encrypt_credential(
                request.app.state.settings, credential or ""
            )
        elif changing_mode:
            item.credential_ciphertext = None
        item.target_fingerprint = next_fingerprint
        item.announce_brew_started = payload.announce_brew_started
        item.mention_channel_on_started = payload.mention_channel_on_started
        item.announce_ready_to_rate = payload.announce_ready_to_rate
        item.mention_channel_on_ready = payload.mention_channel_on_ready

        if payload.auth_mode == "pat":
            if verification is not None:
                item.account_user_id = verification.user_id
                item.account_username = verification.username
            if selected_channel is not None:
                item.team_id = selected_channel.team_id
                item.team_name = selected_channel.team_display_name
                item.channel_id = selected_channel.channel_id
                item.channel_name = selected_channel.channel_name
                item.channel_display_name = selected_channel.channel_display_name
            else:
                item.team_id = payload.team_id
                item.team_name = payload.team_name
                item.channel_id = payload.channel_id
                item.channel_name = payload.channel_name
                item.channel_display_name = payload.channel_display_name
        else:
            item.account_user_id = None
            item.account_username = None
            item.team_id = None
            item.team_name = None
            item.channel_id = None
            item.channel_name = None
            item.channel_display_name = None
        if destination_changed or new_credential is not None:
            item.last_error = None
            item.last_error_at = None
        db.commit()
        return mattermost_settings_response(request, db)
    except MattermostError as exc:
        db.rollback()
        raise_mattermost_http_error(exc)


@router.delete("/settings/mattermost/credential", response_model=MattermostSettingsResponse)
def clear_mattermost_credential(
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> MattermostSettingsResponse:
    require_mattermost_mutation_admin(request, login_session)
    item = get_integration(db)
    item.enabled = False
    item.credential_ciphertext = None
    item.target_fingerprint = None
    item.account_user_id = None
    item.account_username = None
    item.team_id = None
    item.team_name = None
    item.channel_id = None
    item.channel_name = None
    item.channel_display_name = None
    item.last_error = None
    item.last_error_at = None
    cancel_stale_target_notifications(db, None)
    db.commit()
    return mattermost_settings_response(request, db)


@router.post("/settings/mattermost/test", response_model=MattermostTestResponse)
def test_mattermost_delivery(
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> MattermostTestResponse:
    require_mattermost_mutation_admin(request, login_session)
    item = get_integration(db)
    try:
        credential = decrypt_credential(request.app.state.settings, item.credential_ciphertext)
        MattermostClient(item.server_url, credential, item.auth_mode).send(
            channel_id=item.channel_id,
            message=(
                "☕ **Filter Coffee Club connection test**\n"
                "Mattermost notifications are configured. No brew announcement was created."
            ),
            pending_post_id=f"fcc-test-{secrets.token_urlsafe(12)}",
        )
    except MattermostError as exc:
        item.last_error = str(exc)
        item.last_error_at = utcnow()
        db.commit()
        raise_mattermost_http_error(exc)
    item.last_tested_at = utcnow()
    item.last_error = None
    item.last_error_at = None
    db.commit()
    return MattermostTestResponse(delivered=True, message="Test message delivered")


@router.post("/settings/mattermost/retry", response_model=MattermostRetryResponse)
def retry_mattermost_deliveries(
    request: Request,
    db: Session = Depends(session_dependency),
    login_session: LoginSession = Depends(require_csrf),
) -> MattermostRetryResponse:
    require_mattermost_mutation_admin(request, login_session)
    item = get_integration(db)
    if not item.enabled or not item.target_fingerprint:
        raise HTTPException(status_code=409, detail="Mattermost delivery is not enabled")
    result = db.execute(
        update(MattermostNotification)
        .where(
            MattermostNotification.state == "failed",
            MattermostNotification.target_fingerprint == item.target_fingerprint,
        )
        .values(
            state="pending",
            next_attempt_at=utcnow(),
            last_error=None,
        )
    )
    item.last_error = None
    item.last_error_at = None
    db.commit()
    return MattermostRetryResponse(requeued=result.rowcount or 0)
