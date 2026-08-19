from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from .calculations import brew_ratio
from .config import Settings
from .db import utcnow
from .models import Brew, MattermostIntegration, MattermostNotification
from .schemas import MattermostChannelOption, MattermostVerifyResponse

DEFAULT_MATTERMOST_SERVER = "https://mattermost.web.cern.ch"
DELIVERY_TIMEOUT_SECONDS = 10.0
MAX_DELIVERY_AGE = timedelta(hours=24)
POLL_INTERVAL_SECONDS = 5.0
RECONCILIATION_PAGE_SIZE = 200
MAX_RECONCILIATION_PAGES = 50
RECONCILIATION_CLOCK_SKEW = timedelta(minutes=5)
logger = logging.getLogger("fcc.mattermost")
CANCELLABLE_NOTIFICATION_STATES = ("pending", "failed", "delivering")


class MattermostError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class DeliveryTarget:
    server_url: str
    auth_mode: str
    credential: str
    channel_id: str | None


def _normalized_parts(value: str, *, base_only: bool) -> SplitResult:
    candidate = value.strip()
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:
        raise MattermostError("Mattermost URL is invalid") from exc
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not hostname:
        raise MattermostError("Mattermost URL must be an absolute HTTP or HTTPS URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise MattermostError("Mattermost URL must not contain credentials, a query, or a fragment")
    if parts.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise MattermostError("Mattermost connections must use HTTPS")
    if base_only and parts.path not in {"", "/"}:
        raise MattermostError("Mattermost server URL must not contain a path")
    host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return SplitResult(parts.scheme.lower(), netloc, parts.path, "", "")


def normalize_server_url(value: str) -> str:
    parts = _normalized_parts(value, base_only=True)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _origin(parts: SplitResult) -> tuple[str, str, int]:
    hostname = (parts.hostname or "").lower()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme.lower(), hostname, port


def normalize_webhook_url(value: str, server_url: str) -> str:
    parts = _normalized_parts(value, base_only=False)
    server_parts = urlsplit(normalize_server_url(server_url))
    if _origin(parts) != _origin(server_parts):
        raise MattermostError("Webhook URL must belong to the configured Mattermost server")
    path_parts = [item for item in parts.path.split("/") if item]
    if len(path_parts) != 2 or path_parts[0] != "hooks" or not path_parts[1]:
        raise MattermostError("Mattermost webhook URL must use the /hooks/<token> path")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _fernet(settings: Settings) -> Fernet:
    raw_key = (settings.mattermost_secret_key or "").strip()
    if not raw_key:
        raise MattermostError(
            "Mattermost secret encryption is unavailable; configure FCC_MATTERMOST_SECRET_KEY"
        )
    try:
        return Fernet(raw_key.encode())
    except (TypeError, ValueError) as exc:
        raise MattermostError("FCC_MATTERMOST_SECRET_KEY is not a valid Fernet key") from exc


def encryption_available(settings: Settings) -> bool:
    try:
        _fernet(settings)
    except MattermostError:
        return False
    return True


def encrypt_credential(settings: Settings, credential: str) -> str:
    value = credential.strip()
    if not value:
        raise MattermostError("Mattermost credential must not be empty")
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt_credential(settings: Settings, ciphertext: str | None) -> str:
    if not ciphertext:
        raise MattermostError("Mattermost credential is not configured")
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise MattermostError(
            "Mattermost credential cannot be decrypted; re-enter it with the current key"
        ) from exc


def get_integration(db: Session) -> MattermostIntegration:
    integration = db.get(MattermostIntegration, 1)
    if integration is None:
        integration = MattermostIntegration(id=1)
        db.add(integration)
        db.flush()
    return integration


def target_fingerprint(
    *, auth_mode: str, server_url: str, channel_id: str | None, credential: str
) -> str:
    if auth_mode == "pat":
        target = f"pat\0{server_url}\0{channel_id or ''}"
    else:
        webhook_hash = hashlib.sha256(credential.encode()).hexdigest()
        target = f"webhook\0{server_url}\0{webhook_hash}"
    return hashlib.sha256(target.encode()).hexdigest()


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0, math.ceil((retry_at - datetime.now(UTC)).total_seconds()))


class MattermostClient:
    def __init__(self, server_url: str, credential: str, auth_mode: str) -> None:
        self.server_url = normalize_server_url(server_url)
        self.auth_mode = auth_mode
        self.credential = (
            normalize_webhook_url(credential, self.server_url)
            if auth_mode == "webhook"
            else credential.strip()
        )
        if auth_mode == "pat" and not self.credential:
            raise MattermostError("Mattermost personal access token must not be empty")

    def _request(
        self, method: str, url: str, *, json: dict[str, object] | None = None
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.credential}"} if self.auth_mode == "pat" else {}
        try:
            with httpx.Client(
                timeout=DELIVERY_TIMEOUT_SECONDS,
                follow_redirects=False,
                verify=True,
            ) as client:
                response = client.request(method, url, headers=headers, json=json)
        except httpx.RequestError as exc:
            raise MattermostError("Mattermost could not be reached", retryable=True) from exc
        if response.is_redirect:
            raise MattermostError("Mattermost returned an unexpected redirect")
        if response.status_code >= 400:
            retryable = response.status_code in {408, 429} or response.status_code >= 500
            if response.status_code in {401, 403}:
                message = "Mattermost rejected the credential or its permissions"
            elif response.status_code == 404:
                message = "Mattermost destination was not found"
            elif response.status_code == 429:
                message = "Mattermost rate limit was reached"
            else:
                message = f"Mattermost request failed with status {response.status_code}"
            raise MattermostError(
                message,
                retryable=retryable,
                retry_after_seconds=_retry_after(response),
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise MattermostError(
                "Mattermost returned an invalid response",
                retryable=True,
            ) from exc

    def verify_pat(self) -> MattermostVerifyResponse:
        if self.auth_mode != "pat":
            raise MattermostError("Only personal access tokens can discover channels")
        user = self._json(self._request("GET", f"{self.server_url}/api/v4/users/me"))
        teams = self._json(self._request("GET", f"{self.server_url}/api/v4/users/me/teams"))
        if not isinstance(user, dict) or not isinstance(teams, list):
            raise MattermostError("Mattermost returned an invalid account response", retryable=True)
        channels: list[MattermostChannelOption] = []
        for team in teams:
            if not isinstance(team, dict):
                raise MattermostError(
                    "Mattermost returned an invalid team response", retryable=True
                )
            team_id = str(team.get("id", ""))
            if not team_id:
                continue
            team_channels = self._json(
                self._request("GET", f"{self.server_url}/api/v4/users/me/teams/{team_id}/channels")
            )
            if not isinstance(team_channels, list):
                raise MattermostError(
                    "Mattermost returned an invalid channel response", retryable=True
                )
            for channel in team_channels:
                if not isinstance(channel, dict):
                    raise MattermostError(
                        "Mattermost returned an invalid channel response", retryable=True
                    )
                if channel.get("type") not in {"O", "P"} or channel.get("delete_at", 0):
                    continue
                channels.append(
                    MattermostChannelOption(
                        team_id=team_id,
                        team_name=str(team.get("name", "")),
                        team_display_name=str(team.get("display_name") or team.get("name", "")),
                        channel_id=str(channel.get("id", "")),
                        channel_name=str(channel.get("name", "")),
                        channel_display_name=str(
                            channel.get("display_name") or channel.get("name", "")
                        ),
                    )
                )
        channels.sort(
            key=lambda item: (
                item.team_display_name.casefold(),
                item.channel_display_name.casefold(),
            )
        )
        return MattermostVerifyResponse(
            user_id=str(user.get("id", "")),
            username=str(user.get("username", "")),
            channels=channels,
        )

    def find_post_by_pending_id(
        self,
        *,
        channel_id: str,
        pending_post_id: str,
        notification_created_at: datetime,
    ) -> str | None:
        if self.auth_mode != "pat":
            return None
        cutoff_ms = math.floor(
            (notification_created_at - RECONCILIATION_CLOCK_SKEW).timestamp() * 1000
        )
        for page in range(MAX_RECONCILIATION_PAGES):
            payload = self._json(
                self._request(
                    "GET",
                    (
                        f"{self.server_url}/api/v4/channels/{channel_id}/posts"
                        f"?page={page}&per_page={RECONCILIATION_PAGE_SIZE}"
                    ),
                )
            )
            if not isinstance(payload, dict):
                raise MattermostError(
                    "Mattermost returned an invalid post-history response", retryable=True
                )
            order = payload.get("order")
            posts = payload.get("posts")
            if not isinstance(order, list) or not isinstance(posts, dict):
                raise MattermostError(
                    "Mattermost returned an invalid post-history response", retryable=True
                )
            if not order:
                return None
            oldest_create_at: int | None = None
            for post_id in order:
                post = posts.get(post_id)
                if not isinstance(post, dict):
                    continue
                if post.get("pending_post_id") == pending_post_id:
                    return str(post.get("id") or post_id)
                create_at = post.get("create_at")
                if isinstance(create_at, int):
                    oldest_create_at = (
                        create_at if oldest_create_at is None else min(oldest_create_at, create_at)
                    )
            if len(order) < RECONCILIATION_PAGE_SIZE:
                return None
            if oldest_create_at is not None and oldest_create_at < cutoff_ms:
                return None
        raise MattermostError(
            "Mattermost post history is too busy to reconcile this delivery safely",
            retryable=True,
        )

    def send(
        self,
        *,
        channel_id: str | None,
        message: str,
        pending_post_id: str,
        notification_created_at: datetime | None = None,
        reconcile: bool = False,
    ) -> str | None:
        if self.auth_mode == "pat":
            if not channel_id:
                raise MattermostError("Mattermost channel is not configured")
            if reconcile:
                if notification_created_at is None:
                    raise MattermostError("Mattermost retry is missing its creation timestamp")
                existing_post_id = self.find_post_by_pending_id(
                    channel_id=channel_id,
                    pending_post_id=pending_post_id,
                    notification_created_at=notification_created_at,
                )
                if existing_post_id is not None:
                    return existing_post_id
            response = self._request(
                "POST",
                f"{self.server_url}/api/v4/posts",
                json={
                    "channel_id": channel_id,
                    "message": message,
                    "pending_post_id": pending_post_id,
                },
            )
            payload = self._json(response)
            if not isinstance(payload, dict):
                raise MattermostError(
                    "Mattermost returned an invalid post response", retryable=True
                )
            return str(payload.get("id", "")) or None
        self._request("POST", self.credential, json={"text": message})
        return None


def _safe_markdown(value: str) -> str:
    safe = value.replace("\\", "\\\\")
    for character in ("`", "*", "_", "~", "[", "]"):
        safe = safe.replace(character, f"\\{character}")
    return safe.replace("@", "@\u200b")


def _amount(value: float) -> str:
    return f"{value:g}"


def build_brew_message(
    brew: Brew,
    event_type: Literal["brew_started", "ready_to_rate"],
    public_base_url: str,
    mention_channel: bool,
) -> str:
    coffee = f"{_safe_markdown(brew.coffee.roaster)} · {_safe_markdown(brew.coffee.name)}"
    operators = ", ".join(_safe_markdown(item.display_name) for item in brew.operators)
    summary = (
        f"{_amount(brew.dose_g)} g coffee → {_amount(brew.water_g)} g water · "
        f"1:{brew_ratio(brew.water_g, brew.dose_g):g} · {_amount(brew.temperature_c)} °C"
    )
    base_url = public_base_url.rstrip("/")
    prefix = "@channel\n" if mention_channel else ""
    if event_type == "brew_started":
        heading = f"☕ **Brew #{brew.id} started** — {coffee}"
        link = f"[Follow the brew]({base_url}/brews/{brew.id})"
    else:
        heading = f"⭐ **Brew #{brew.id} is ready to rate** — {coffee}"
        if not brew.rating_token:
            raise MattermostError("Completed brew has no rating token")
        link = f"[Rate this brew]({base_url}/rate/{brew.rating_token})"
    return f"{prefix}{heading}\n{operators} · {summary}\n{link}"


def enqueue_brew_notification(
    db: Session,
    brew: Brew,
    event_type: Literal["brew_started", "ready_to_rate"],
    public_base_url: str,
    *,
    demo_mode: bool,
) -> None:
    if demo_mode:
        return
    integration = db.get(MattermostIntegration, 1)
    if (
        integration is None
        or not integration.enabled
        or not integration.credential_ciphertext
        or not integration.target_fingerprint
    ):
        return
    if event_type == "brew_started":
        if not integration.announce_brew_started:
            return
        mention = integration.mention_channel_on_started
    else:
        if not integration.announce_ready_to_rate:
            return
        mention = integration.mention_channel_on_ready
    if brew.id is None:
        db.flush()
    now = utcnow()
    db.add(
        MattermostNotification(
            brew_id=brew.id,
            event_type=event_type,
            message=build_brew_message(brew, event_type, public_base_url, mention),
            target_fingerprint=integration.target_fingerprint,
            pending_post_id=f"{secrets.token_urlsafe(18)}:{math.floor(now.timestamp() * 1000)}",
            state="pending",
            next_attempt_at=now,
        )
    )


def cancel_brew_notifications(db: Session, brew_id: int) -> None:
    db.execute(
        update(MattermostNotification)
        .where(
            MattermostNotification.brew_id == brew_id,
            MattermostNotification.state.in_(CANCELLABLE_NOTIFICATION_STATES),
        )
        .values(state="cancelled", next_attempt_at=None)
    )


def cancel_stale_target_notifications(db: Session, target: str | None) -> None:
    conditions = [MattermostNotification.state.in_(CANCELLABLE_NOTIFICATION_STATES)]
    if target is not None:
        conditions.append(MattermostNotification.target_fingerprint != target)
    db.execute(
        update(MattermostNotification)
        .where(*conditions)
        .values(state="cancelled", next_attempt_at=None)
    )


def queue_counts(db: Session) -> tuple[int, int]:
    rows = dict(
        db.execute(
            select(MattermostNotification.state, func.count(MattermostNotification.id))
            .where(MattermostNotification.state.in_(("pending", "failed", "delivering")))
            .group_by(MattermostNotification.state)
        ).all()
    )
    return rows.get("pending", 0) + rows.get("delivering", 0), rows.get("failed", 0)


def _set_delivery_failure(
    factory: sessionmaker[Session], notification_id: int, error: MattermostError
) -> None:
    with factory() as db:
        item = db.get(MattermostNotification, notification_id)
        if item is None or item.state != "delivering":
            return
        integration = db.get(MattermostIntegration, 1)
        now = utcnow()
        age = now - item.created_at
        if error.retryable and age < MAX_DELIVERY_AGE:
            delay = min(3600, 30 * (2 ** max(0, item.attempt_count - 1)))
            if error.retry_after_seconds is not None:
                delay = max(delay, error.retry_after_seconds)
            item.state = "pending"
            item.next_attempt_at = now + timedelta(seconds=delay)
        else:
            item.state = "failed"
            item.next_attempt_at = None
        item.last_error = str(error)
        if integration and integration.target_fingerprint == item.target_fingerprint:
            integration.last_error = str(error)
            integration.last_error_at = now
        db.commit()
    logger.warning(
        "mattermost_delivery_failed",
        extra={"fields": {"notification_id": notification_id, "error": str(error)}},
    )


def _load_delivery_target(
    settings: Settings,
    factory: sessionmaker[Session],
    notification_id: int,
    fingerprint: str,
) -> DeliveryTarget | None:
    with factory() as db:
        item = db.get(MattermostNotification, notification_id)
        if item is None or item.state != "delivering":
            return None
        integration = db.get(MattermostIntegration, 1)
        if (
            integration is None
            or not integration.enabled
            or integration.target_fingerprint != fingerprint
        ):
            item.state = "cancelled"
            item.next_attempt_at = None
            db.commit()
            return None
        return DeliveryTarget(
            server_url=integration.server_url,
            auth_mode=integration.auth_mode,
            credential=decrypt_credential(settings, integration.credential_ciphertext),
            channel_id=integration.channel_id,
        )


def deliver_one(settings: Settings, factory: sessionmaker[Session]) -> bool:
    now = utcnow()
    with factory() as db:
        candidate_id = (
            select(MattermostNotification)
            .with_only_columns(MattermostNotification.id)
            .where(
                MattermostNotification.state == "pending",
                or_(
                    MattermostNotification.next_attempt_at.is_(None),
                    MattermostNotification.next_attempt_at <= now,
                ),
            )
            .order_by(MattermostNotification.created_at, MattermostNotification.id)
            .limit(1)
            .scalar_subquery()
        )
        notification_id = db.scalar(
            update(MattermostNotification)
            .where(
                MattermostNotification.id == candidate_id,
                MattermostNotification.state == "pending",
            )
            .values(
                state="delivering",
                attempt_count=MattermostNotification.attempt_count + 1,
                last_attempt_at=now,
                next_attempt_at=None,
            )
            .returning(MattermostNotification.id)
            .execution_options(synchronize_session=False)
        )
        if notification_id is None:
            return False
        item = db.get(MattermostNotification, notification_id)
        if item is None:
            db.rollback()
            return False
        message = item.message
        fingerprint = item.target_fingerprint
        pending_post_id = item.pending_post_id
        notification_created_at = item.created_at
        reconcile = item.attempt_count > 1
        db.commit()

    try:
        target = _load_delivery_target(settings, factory, notification_id, fingerprint)
        if target is None:
            return True
        post_id = MattermostClient(
            target.server_url,
            target.credential,
            target.auth_mode,
        ).send(
            channel_id=target.channel_id,
            message=message,
            pending_post_id=pending_post_id,
            notification_created_at=notification_created_at,
            reconcile=reconcile,
        )
    except MattermostError as exc:
        _set_delivery_failure(factory, notification_id, exc)
        return True
    except Exception:
        logger.exception(
            "mattermost_delivery_unexpected_error",
            extra={"fields": {"notification_id": notification_id}},
        )
        _set_delivery_failure(
            factory,
            notification_id,
            MattermostError("Unexpected Mattermost delivery failure", retryable=True),
        )
        return True

    with factory() as db:
        delivered = db.get(MattermostNotification, notification_id)
        integration = db.get(MattermostIntegration, 1)
        delivered_at = utcnow()
        if delivered and delivered.state == "delivering":
            delivered.state = "sent"
            delivered.sent_at = delivered_at
            delivered.last_error = None
            delivered.mattermost_post_id = post_id
        if integration and integration.target_fingerprint == fingerprint:
            integration.last_delivery_at = delivered_at
            integration.last_error = None
            integration.last_error_at = None
        db.commit()
    logger.info(
        "mattermost_delivery_complete",
        extra={"fields": {"notification_id": notification_id}},
    )
    return True


def recover_interrupted_deliveries(factory: sessionmaker[Session]) -> None:
    with factory() as db:
        db.execute(
            update(MattermostNotification)
            .where(MattermostNotification.state == "delivering")
            .values(state="pending", next_attempt_at=utcnow())
        )
        db.commit()


async def delivery_worker(settings: Settings, factory: sessionmaker[Session]) -> None:
    recovery_needed = True
    while True:
        try:
            if recovery_needed:
                await asyncio.to_thread(recover_interrupted_deliveries, factory)
                recovery_needed = False
            delivered = await asyncio.to_thread(deliver_one, settings, factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            recovery_needed = True
            logger.exception("mattermost_delivery_worker_error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        if not delivered:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
