from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from threading import Event, Lock

import httpx
import pytest
from app import mattermost as mattermost_module
from app.config import Settings
from app.db import Base, build_engine, build_session_factory, utcnow
from app.mattermost import (
    MattermostClient,
    MattermostError,
    _retry_after,
    build_brew_message,
    cancel_brew_notifications,
    decrypt_credential,
    deliver_one,
    delivery_worker,
    encrypt_credential,
    normalize_server_url,
    normalize_webhook_url,
    recover_interrupted_deliveries,
    target_fingerprint,
)
from app.models import (
    Brew,
    Coffee,
    Grinder,
    MattermostIntegration,
    MattermostNotification,
    Profile,
)
from cryptography.fernet import Fernet


def test_mattermost_urls_require_safe_matching_origins() -> None:
    assert normalize_server_url("https://mattermost.web.cern.ch/") == (
        "https://mattermost.web.cern.ch"
    )
    assert normalize_server_url("http://127.0.0.1:8065") == "http://127.0.0.1:8065"
    assert (
        normalize_webhook_url(
            "https://mattermost.web.cern.ch/hooks/secret-token/",
            "https://mattermost.web.cern.ch",
        )
        == "https://mattermost.web.cern.ch/hooks/secret-token"
    )

    invalid_servers = [
        "http://mattermost.example",
        "https://user:pass@mattermost.example",
        "https://mattermost.example/api/v4",
        "https://mattermost.example?token=secret",
    ]
    for value in invalid_servers:
        with pytest.raises(MattermostError):
            normalize_server_url(value)
    with pytest.raises(MattermostError, match="configured Mattermost server"):
        normalize_webhook_url(
            "https://attacker.example/hooks/secret",
            "https://mattermost.web.cern.ch",
        )


def test_retry_after_accepts_seconds_and_http_dates() -> None:
    seconds = httpx.Response(429, headers={"Retry-After": "47"})
    assert _retry_after(seconds) == 47

    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    dated = httpx.Response(429, headers={"Retry-After": format_datetime(retry_at, usegmt=True)})
    parsed_delay = _retry_after(dated)
    assert parsed_delay is not None
    assert 58 <= parsed_delay <= 60


def test_mattermost_credentials_are_encrypted_and_key_bound(tmp_path) -> None:  # type: ignore[no-untyped-def]
    key = Fernet.generate_key().decode()
    settings = Settings(data_dir=tmp_path, mattermost_secret_key=key)
    ciphertext = encrypt_credential(settings, "super-secret-token")
    assert "super-secret-token" not in ciphertext
    assert decrypt_credential(settings, ciphertext) == "super-secret-token"

    wrong_settings = Settings(
        data_dir=tmp_path,
        mattermost_secret_key=Fernet.generate_key().decode(),
    )
    with pytest.raises(MattermostError, match="cannot be decrypted"):
        decrypt_credential(wrong_settings, ciphertext)


def test_brew_messages_only_emit_the_configured_channel_mention() -> None:
    coffee = Coffee(
        id=4,
        roaster="Orbit @channel",
        name="Kenya [lot] @ada",
        chart_color="#0072B2",
        created_by_id=1,
    )
    operator = Profile(id=1, display_name="Ada @all", pin_hash="hash")
    brew = Brew(
        id=9,
        coffee_id=coffee.id,
        coffee=coffee,
        operator_id=operator.id,
        operators=[operator],
        grinder_id=1,
        dose_g=15,
        water_g=240,
        target_ratio=16,
        temperature_c=94,
        grinder_setting=30,
        servings=2,
        rating_token="rating-secret",
    )

    started = build_brew_message(brew, "brew_started", "https://coffee.example", True)
    ready = build_brew_message(brew, "ready_to_rate", "https://coffee.example", False)
    assert started.startswith("@channel\n")
    assert started.count("@channel") == 1
    assert "@\u200bchannel" in started
    assert "@\u200ball" in started
    assert "https://coffee.example/brews/9" in started
    assert "@channel" not in ready
    assert "https://coffee.example/rate/rating-secret" in ready


def test_target_fingerprint_rotates_for_destinations_but_not_pat_tokens() -> None:
    first_pat = target_fingerprint(
        auth_mode="pat",
        server_url="https://mattermost.example",
        channel_id="channel-1",
        credential="token-one",
    )
    rotated_pat = target_fingerprint(
        auth_mode="pat",
        server_url="https://mattermost.example",
        channel_id="channel-1",
        credential="token-two",
    )
    other_channel = target_fingerprint(
        auth_mode="pat",
        server_url="https://mattermost.example",
        channel_id="channel-2",
        credential="token-two",
    )
    assert first_pat == rotated_pat
    assert first_pat != other_channel

    first_webhook = target_fingerprint(
        auth_mode="webhook",
        server_url="https://mattermost.example",
        channel_id=None,
        credential="https://mattermost.example/hooks/one",
    )
    second_webhook = target_fingerprint(
        auth_mode="webhook",
        server_url="https://mattermost.example",
        channel_id=None,
        credential="https://mattermost.example/hooks/two",
    )
    assert first_webhook != second_webhook


def test_webhook_posts_text_to_bound_url_without_bearer_auth(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    requests: list[tuple[str, str, dict[str, object] | None, dict[str, str]]] = []

    class FakeResponse:
        status_code = 200
        is_redirect = False
        headers: dict[str, str] = {}

    class FakeHttpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeHttpClient:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object] | None,
        ) -> FakeResponse:
            requests.append((method, url, json, headers))
            return FakeResponse()

    monkeypatch.setattr("app.mattermost.httpx.Client", FakeHttpClient)
    client = MattermostClient(
        "https://mattermost.web.cern.ch",
        "https://mattermost.web.cern.ch/hooks/webhook-secret",
        "webhook",
    )

    post_id = client.send(
        channel_id=None,
        message="Coffee is ready",
        pending_post_id="unused-for-webhooks",
    )

    assert post_id is None
    assert requests == [
        (
            "POST",
            "https://mattermost.web.cern.ch/hooks/webhook-secret",
            {"text": "Coffee is ready"},
            {},
        )
    ]


@pytest.mark.parametrize(
    ("status_code", "retryable", "message"),
    [
        (302, False, "unexpected redirect"),
        (404, False, "destination was not found"),
        (429, True, "rate limit was reached"),
        (503, True, "status 503"),
    ],
)
def test_webhook_classifies_http_failures_without_exposing_its_url(
    monkeypatch,
    status_code: int,
    retryable: bool,
    message: str,
) -> None:  # type: ignore[no-untyped-def]
    real_client = httpx.Client

    def respond(_request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": "75"} if status_code == 429 else {}
        return httpx.Response(status_code, headers=headers)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        "app.mattermost.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    client = MattermostClient(
        "https://mattermost.web.cern.ch",
        "https://mattermost.web.cern.ch/hooks/webhook-secret",
        "webhook",
    )

    with pytest.raises(MattermostError, match=message) as caught:
        client.send(
            channel_id=None,
            message="Coffee is ready",
            pending_post_id="unused-for-webhooks",
        )

    assert caught.value.retryable is retryable
    assert "webhook-secret" not in str(caught.value)
    assert caught.value.retry_after_seconds == (75 if status_code == 429 else None)


def test_webhook_treats_transport_failures_as_retryable_without_exposing_its_url(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    real_client = httpx.Client

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(fail)
    monkeypatch.setattr(
        "app.mattermost.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    client = MattermostClient(
        "https://mattermost.web.cern.ch",
        "https://mattermost.web.cern.ch/hooks/webhook-secret",
        "webhook",
    )

    with pytest.raises(MattermostError, match="could not be reached") as caught:
        client.send(
            channel_id=None,
            message="Coffee is ready",
            pending_post_id="unused-for-webhooks",
        )

    assert caught.value.retryable is True
    assert "webhook-secret" not in str(caught.value)


def test_pat_verification_filters_channels_and_posts_with_deduplication(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    requests: list[tuple[str, str, dict[str, object] | None, dict[str, str]]] = []

    class FakeResponse:
        status_code = 200
        is_redirect = False
        headers: dict[str, str] = {}

        def __init__(self, payload: object) -> None:
            self.payload = payload

        def json(self) -> object:
            return self.payload

    class FakeHttpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeHttpClient:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object] | None,
        ) -> FakeResponse:
            requests.append((method, url, json, headers))
            if url.endswith("/users/me"):
                return FakeResponse({"id": "user-1", "username": "coffee-bot"})
            if url.endswith("/users/me/teams"):
                return FakeResponse(
                    [{"id": "team-1", "name": "coffee", "display_name": "Coffee Team"}]
                )
            if url.endswith("/teams/team-1/channels"):
                return FakeResponse(
                    [
                        {
                            "id": "channel-1",
                            "name": "breaks",
                            "display_name": "Coffee breaks",
                            "type": "P",
                            "delete_at": 0,
                        },
                        {
                            "id": "dm-1",
                            "name": "direct",
                            "display_name": "Direct",
                            "type": "D",
                            "delete_at": 0,
                        },
                    ]
                )
            return FakeResponse({"id": "post-1"})

    monkeypatch.setattr("app.mattermost.httpx.Client", FakeHttpClient)
    client = MattermostClient("https://mattermost.example", "pat-secret", "pat")
    verified = client.verify_pat()
    assert verified.username == "coffee-bot"
    assert [channel.channel_id for channel in verified.channels] == ["channel-1"]

    post_id = client.send(
        channel_id="channel-1",
        message="Coffee is ready",
        pending_post_id="stable-client-id",
    )
    assert post_id == "post-1"
    post_request = requests[-1]
    assert post_request[2] == {
        "channel_id": "channel-1",
        "message": "Coffee is ready",
        "pending_post_id": "stable-client-id",
    }
    assert post_request[3] == {"Authorization": "Bearer pat-secret"}


def test_pat_retry_reconciles_an_existing_post_before_sending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    requests: list[tuple[str, str]] = []

    class FakeResponse:
        def json(self) -> object:
            return {
                "order": ["post-1"],
                "posts": {
                    "post-1": {
                        "id": "post-1",
                        "create_at": math.floor(datetime.now(UTC).timestamp() * 1000),
                        "pending_post_id": "stable-client-id",
                    }
                },
            }

    def fake_request(
        _client: MattermostClient,
        method: str,
        url: str,
        *,
        json: dict[str, object] | None = None,
    ) -> FakeResponse:
        del json
        requests.append((method, url))
        return FakeResponse()

    monkeypatch.setattr(MattermostClient, "_request", fake_request)
    client = MattermostClient("https://mattermost.example", "pat-secret", "pat")
    post_id = client.send(
        channel_id="channel-1",
        message="Coffee is ready",
        pending_post_id="stable-client-id",
        notification_created_at=datetime.now(UTC) - timedelta(minutes=1),
        reconcile=True,
    )

    assert post_id == "post-1"
    assert [method for method, _url in requests] == ["GET"]
    assert "/channels/channel-1/posts?page=0&per_page=200" in requests[0][1]


def delivery_database(tmp_path):  # type: ignore[no-untyped-def]
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'mattermost-delivery.sqlite3'}",
        mattermost_secret_key=Fernet.generate_key().decode(),
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    fingerprint = target_fingerprint(
        auth_mode="pat",
        server_url="https://mattermost.example",
        channel_id="channel-1",
        credential="pat-secret",
    )
    with factory() as db:
        profile = Profile(id=1, display_name="Ada", pin_hash="hash")
        db.add(profile)
        db.flush()
        coffee = Coffee(
            id=1,
            roaster="Orbit",
            name="Kenya",
            chart_color="#0072B2",
            created_by_id=1,
        )
        grinder = Grinder(id=1, manufacturer="Comandante", model="C40")
        db.add_all([coffee, grinder])
        db.flush()
        brew = Brew(
            id=1,
            coffee_id=1,
            operator_id=1,
            operators=[profile],
            grinder_id=1,
            dose_g=15,
            water_g=240,
            target_ratio=16,
            temperature_c=94,
            grinder_setting=30,
            servings=1,
        )
        db.add(brew)
        db.flush()
        db.add_all(
            [
                MattermostIntegration(
                    id=1,
                    enabled=True,
                    server_url="https://mattermost.example",
                    auth_mode="pat",
                    credential_ciphertext=encrypt_credential(settings, "pat-secret"),
                    channel_id="channel-1",
                    target_fingerprint=fingerprint,
                ),
                MattermostNotification(
                    id=1,
                    brew_id=1,
                    event_type="brew_started",
                    message="Coffee is brewing",
                    target_fingerprint=fingerprint,
                    pending_post_id="stable-pending-post",
                    state="pending",
                    next_attempt_at=utcnow(),
                ),
            ]
        )
        db.commit()
    return settings, engine, factory


def test_delivery_marks_success_and_preserves_pending_post_id(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings, engine, factory = delivery_database(tmp_path)
    sent: list[dict[str, object]] = []

    def fake_send(_client, **kwargs: object) -> str:  # type: ignore[no-untyped-def]
        sent.append(kwargs)
        return "mattermost-post-1"

    monkeypatch.setattr(MattermostClient, "send", fake_send)
    assert deliver_one(settings, factory) is True
    with factory() as db:
        item = db.get(MattermostNotification, 1)
        integration = db.get(MattermostIntegration, 1)
        assert item is not None and item.state == "sent"
        assert item.mattermost_post_id == "mattermost-post-1"
        assert item.sent_at is not None
        assert integration is not None and integration.last_delivery_at is not None
    assert sent[0]["pending_post_id"] == "stable-pending-post"
    engine.dispose()


def test_delivery_retries_transient_errors_and_fails_permission_errors(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    settings, engine, factory = delivery_database(tmp_path)

    def transient_failure(_client, **_kwargs: object) -> str:  # type: ignore[no-untyped-def]
        raise MattermostError("Mattermost is unavailable", retryable=True)

    monkeypatch.setattr(MattermostClient, "send", transient_failure)
    before = utcnow()
    assert deliver_one(settings, factory) is True
    with factory() as db:
        item = db.get(MattermostNotification, 1)
        assert item is not None and item.state == "pending"
        assert item.attempt_count == 1
        assert item.next_attempt_at is not None
        assert item.next_attempt_at >= before
        item.next_attempt_at = utcnow()
        db.commit()

    def permission_failure(_client, **_kwargs: object) -> str:  # type: ignore[no-untyped-def]
        raise MattermostError("Mattermost rejected the credential or its permissions")

    monkeypatch.setattr(MattermostClient, "send", permission_failure)
    assert deliver_one(settings, factory) is True
    with factory() as db:
        item = db.get(MattermostNotification, 1)
        integration = db.get(MattermostIntegration, 1)
        assert item is not None and item.state == "failed"
        assert item.attempt_count == 2
        assert integration is not None
        assert integration.last_error == "Mattermost rejected the credential or its permissions"
    engine.dispose()


def test_delivery_claim_is_atomic_across_workers(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings, engine, factory = delivery_database(tmp_path)
    send_started = Event()
    release_send = Event()
    sent_count = 0
    sent_lock = Lock()

    def blocking_send(_client, **_kwargs: object) -> str:  # type: ignore[no-untyped-def]
        nonlocal sent_count
        with sent_lock:
            sent_count += 1
        send_started.set()
        assert release_send.wait(timeout=5)
        return "mattermost-post-1"

    monkeypatch.setattr(MattermostClient, "send", blocking_send)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(deliver_one, settings, factory)
        assert send_started.wait(timeout=5)
        second = executor.submit(deliver_one, settings, factory)
        assert second.result(timeout=5) is False
        release_send.set()
        assert first.result(timeout=5) is True

    assert sent_count == 1
    engine.dispose()


def test_cancelling_brew_stops_a_claimed_delivery_before_target_load(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings, engine, factory = delivery_database(tmp_path)
    target_load_started = Event()
    release_target_load = Event()
    send_calls = 0
    original_load_target = mattermost_module._load_delivery_target

    def blocking_load_target(*args, **kwargs):  # type: ignore[no-untyped-def]
        target_load_started.set()
        assert release_target_load.wait(timeout=5)
        return original_load_target(*args, **kwargs)

    def record_send(_client, **_kwargs: object) -> str:  # type: ignore[no-untyped-def]
        nonlocal send_calls
        send_calls += 1
        return "mattermost-post-1"

    monkeypatch.setattr(mattermost_module, "_load_delivery_target", blocking_load_target)
    monkeypatch.setattr(MattermostClient, "send", record_send)
    with ThreadPoolExecutor(max_workers=1) as executor:
        delivery = executor.submit(deliver_one, settings, factory)
        assert target_load_started.wait(timeout=5)
        with factory() as db:
            cancel_brew_notifications(db, 1)
            db.commit()
        release_target_load.set()
        assert delivery.result(timeout=5) is True

    with factory() as db:
        item = db.get(MattermostNotification, 1)
        assert item is not None and item.state == "cancelled"
    assert send_calls == 0
    engine.dispose()


def test_recovery_requeues_interrupted_deliveries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _settings, engine, factory = delivery_database(tmp_path)
    with factory() as db:
        item = db.get(MattermostNotification, 1)
        assert item is not None
        item.state = "delivering"
        item.next_attempt_at = None
        db.commit()

    recover_interrupted_deliveries(factory)

    with factory() as db:
        item = db.get(MattermostNotification, 1)
        assert item is not None and item.state == "pending"
        assert item.next_attempt_at is not None
    engine.dispose()


def test_delivery_worker_recovers_after_an_unexpected_iteration_error(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    settings, engine, factory = delivery_database(tmp_path)
    delivery_calls = 0
    recovery_calls = 0
    worker_retried = Event()

    def record_recovery(_factory) -> None:  # type: ignore[no-untyped-def]
        nonlocal recovery_calls
        recovery_calls += 1

    def flaky_delivery(_settings, _factory) -> bool:  # type: ignore[no-untyped-def]
        nonlocal delivery_calls
        delivery_calls += 1
        if delivery_calls == 1:
            raise RuntimeError("temporary database failure")
        worker_retried.set()
        return False

    monkeypatch.setattr(mattermost_module, "recover_interrupted_deliveries", record_recovery)
    monkeypatch.setattr(mattermost_module, "deliver_one", flaky_delivery)
    monkeypatch.setattr(mattermost_module, "POLL_INTERVAL_SECONDS", 0)

    async def exercise_worker() -> None:
        task = asyncio.create_task(delivery_worker(settings, factory))
        assert await asyncio.to_thread(worker_retried.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise_worker())
    assert delivery_calls >= 2
    assert recovery_calls >= 2
    engine.dispose()
