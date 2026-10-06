from __future__ import annotations

from pathlib import Path

import pytest
from app import main as main_module
from app import mattermost as mattermost_module
from app.models import (
    MattermostIntegration,
    MattermostNotification,
)
from app.schemas import MattermostVerifyResponse
from cryptography.fernet import Fernet
from sqlalchemy import select

from tests.api_helpers import (
    bootstrap,
    build_client,
    inactive_mattermost_worker,
    mattermost_settings_payload,
    mattermost_verification,
    mattermost_webhook_payload,
)


def test_mattermost_settings_encrypt_verify_test_and_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "delivery_worker", inactive_mattermost_worker)
    verification_calls: list[tuple[str, str]] = []

    def verify_pat(client: mattermost_module.MattermostClient) -> MattermostVerifyResponse:
        verification_calls.append((client.server_url, client.credential))
        return mattermost_verification()

    monkeypatch.setattr(mattermost_module.MattermostClient, "verify_pat", verify_pat)
    sent: list[dict[str, object]] = []

    def capture_send(_client, **kwargs: object) -> str:  # type: ignore[no-untyped-def]
        sent.append(kwargs)
        return "post-1"

    monkeypatch.setattr(mattermost_module.MattermostClient, "send", capture_send)
    encryption_key = Fernet.generate_key().decode()
    with build_client(tmp_path, mattermost_secret_key=encryption_key) as client:
        assert client.get("/api/v1/settings/mattermost").status_code == 401
        _session, headers = bootstrap(client)

        initial = client.get("/api/v1/settings/mattermost").json()
        assert initial["server_url"] == "https://mattermost.web.cern.ch"
        assert initial["auth_mode"] == "webhook"
        assert initial["credential_configured"] is False
        assert initial["encryption_available"] is True
        assert initial["credential_status"] == "not_configured"

        verified = client.post(
            "/api/v1/settings/mattermost/verify",
            headers=headers,
            json={
                "server_url": "https://mattermost.web.cern.ch",
                "credential": "mattermost-secret-token",
            },
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["username"] == "coffee-bot"
        assert verified.json()["channels"][0]["channel_id"] == "channel-1"

        saved = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_settings_payload(),
        )
        assert saved.status_code == 200, saved.text
        saved_payload = saved.json()
        assert saved_payload["credential_configured"] is True
        assert saved_payload["credential_status"] == "ready"
        assert saved_payload["account_username"] == "coffee-bot"
        assert saved_payload["channel_display_name"] == "Coffee breaks"
        assert "credential" not in saved_payload
        assert "mattermost" not in client.get("/api/v1/settings").text.lower()
        assert len(verification_calls) == 2

        preserved_payload = mattermost_settings_payload(
            announce_ready_to_rate=False,
            mention_channel_on_ready=False,
        )
        preserved_payload.pop("credential")
        preserved = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=preserved_payload,
        )
        assert preserved.status_code == 200, preserved.text
        assert preserved.json()["announce_ready_to_rate"] is False
        assert len(verification_calls) == 2

        changed_server_verify = client.post(
            "/api/v1/settings/mattermost/verify",
            headers=headers,
            json={"server_url": "https://attacker.example"},
        )
        assert changed_server_verify.status_code == 422
        assert "Re-enter" in changed_server_verify.text

        changed_server_payload = {**preserved_payload, "server_url": "https://attacker.example"}
        changed_server_save = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=changed_server_payload,
        )
        assert changed_server_save.status_code == 422
        assert "Re-enter" in changed_server_save.text
        assert len(verification_calls) == 2

        with client.app.state.session_factory() as db:
            integration = db.get(MattermostIntegration, 1)
            assert integration is not None
            assert "mattermost-secret-token" not in (integration.credential_ciphertext or "")
            assert integration.server_url == "https://mattermost.web.cern.ch"

        tested = client.post("/api/v1/settings/mattermost/test", headers=headers, json={})
        assert tested.status_code == 200, tested.text
        assert sent[-1]["channel_id"] == "channel-1"
        assert "@channel" not in str(sent[-1]["message"])

        cleared = client.delete("/api/v1/settings/mattermost/credential", headers=headers)
        assert cleared.status_code == 200
        assert cleared.json()["enabled"] is False
        assert cleared.json()["credential_configured"] is False


def test_mattermost_webhook_lifecycle_requires_explicit_mode_and_preserves_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "delivery_worker", inactive_mattermost_worker)
    deliveries: list[dict[str, object]] = []

    def capture_send(client: mattermost_module.MattermostClient, **kwargs: object) -> None:
        deliveries.append(
            {
                "auth_mode": client.auth_mode,
                "credential": client.credential,
                **kwargs,
            }
        )

    monkeypatch.setattr(mattermost_module.MattermostClient, "send", capture_send)
    encryption_key = Fernet.generate_key().decode()
    with build_client(tmp_path, mattermost_secret_key=encryption_key) as client:
        _session, headers = bootstrap(client)

        missing_mode = mattermost_webhook_payload()
        missing_mode.pop("auth_mode")
        rejected_mode = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=missing_mode,
        )
        assert rejected_mode.status_code == 422

        webhook_secret = str(mattermost_webhook_payload()["credential"])
        saved = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_webhook_payload(),
        )
        assert saved.status_code == 200, saved.text
        saved_payload = saved.json()
        assert saved_payload["auth_mode"] == "webhook"
        assert saved_payload["credential_configured"] is True
        assert saved_payload["team_id"] is None
        assert saved_payload["channel_id"] is None
        assert webhook_secret not in saved.text

        with client.app.state.session_factory() as db:
            integration = db.get(MattermostIntegration, 1)
            assert integration is not None
            assert integration.credential_ciphertext is not None
            assert webhook_secret not in integration.credential_ciphertext
            assert (
                mattermost_module.decrypt_credential(
                    client.app.state.settings,
                    integration.credential_ciphertext,
                )
                == "https://mattermost.web.cern.ch/hooks/coffee-webhook"
            )
            original_fingerprint = integration.target_fingerprint

        preserved_payload = mattermost_webhook_payload(announce_ready_to_rate=False)
        preserved_payload.pop("credential")
        preserved = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=preserved_payload,
        )
        assert preserved.status_code == 200, preserved.text
        assert preserved.json()["credential_configured"] is True
        assert preserved.json()["announce_ready_to_rate"] is False

        foreign_webhook = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_webhook_payload(credential="https://attacker.example/hooks/stolen"),
        )
        assert foreign_webhook.status_code == 422
        assert "configured Mattermost server" in foreign_webhook.text

        tested = client.post("/api/v1/settings/mattermost/test", headers=headers, json={})
        assert tested.status_code == 200, tested.text
        assert deliveries[-1]["auth_mode"] == "webhook"
        assert deliveries[-1]["credential"] == "https://mattermost.web.cern.ch/hooks/coffee-webhook"
        assert deliveries[-1]["channel_id"] is None

        rotated_url = "https://mattermost.web.cern.ch/hooks/rotated-webhook"
        rotated = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_webhook_payload(credential=rotated_url),
        )
        assert rotated.status_code == 200, rotated.text
        assert rotated_url not in rotated.text
        with client.app.state.session_factory() as db:
            integration = db.get(MattermostIntegration, 1)
            assert integration is not None
            assert integration.target_fingerprint != original_fingerprint
            assert (
                mattermost_module.decrypt_credential(
                    client.app.state.settings,
                    integration.credential_ciphertext,
                )
                == rotated_url
            )

        switched_to_pat = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json={
                "enabled": False,
                "server_url": "https://mattermost.web.cern.ch",
                "auth_mode": "pat",
            },
        )
        assert switched_to_pat.status_code == 200, switched_to_pat.text
        assert switched_to_pat.json()["auth_mode"] == "pat"
        assert switched_to_pat.json()["credential_configured"] is False
        with client.app.state.session_factory() as db:
            integration = db.get(MattermostIntegration, 1)
            assert integration is not None
            assert integration.credential_ciphertext is None
            assert integration.target_fingerprint is None


def test_mattermost_setup_requires_encryption_key(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        settings = client.get("/api/v1/settings/mattermost").json()
        assert settings["encryption_available"] is False
        assert settings["credential_status"] == "not_configured"
        response = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_settings_payload(),
        )
        assert response.status_code == 422
        assert "FCC_MATTERMOST_SECRET_KEY" in response.text


def test_mattermost_settings_report_unreadable_credential_after_key_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "delivery_worker", inactive_mattermost_worker)
    monkeypatch.setattr(
        mattermost_module.MattermostClient,
        "verify_pat",
        lambda _client: mattermost_verification(),
    )
    first_key = Fernet.generate_key().decode()
    with build_client(tmp_path, mattermost_secret_key=first_key) as client:
        _session, headers = bootstrap(client)
        saved = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_settings_payload(),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["credential_status"] == "ready"

    replacement_key = Fernet.generate_key().decode()
    with build_client(tmp_path, mattermost_secret_key=replacement_key) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        assert login.status_code == 200, login.text
        settings = client.get("/api/v1/settings/mattermost").json()
        assert settings["encryption_available"] is True
        assert settings["credential_configured"] is True
        assert settings["credential_status"] == "unreadable"


def test_mattermost_settings_reject_invalid_encryption_key(tmp_path: Path) -> None:
    with build_client(tmp_path, mattermost_secret_key="not-a-fernet-key") as client:
        _session, headers = bootstrap(client)
        settings = client.get("/api/v1/settings/mattermost").json()
        assert settings["encryption_available"] is False
        assert settings["credential_status"] == "not_configured"
        response = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_webhook_payload(),
        )
        assert response.status_code == 422
        assert "FCC_MATTERMOST_SECRET_KEY" in response.text


def test_mattermost_settings_require_admin_and_csrf(tmp_path: Path) -> None:
    with build_client(tmp_path, mattermost_secret_key=Fernet.generate_key().decode()) as client:
        _session, admin_headers = bootstrap(client)
        without_csrf = client.put(
            "/api/v1/settings/mattermost",
            json=mattermost_settings_payload(),
        )
        assert without_csrf.status_code == 403

        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"pin_change_required": False},
        )
        member_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        member_headers = {"X-CSRF-Token": member_login["csrf_token"]}

        assert client.get("/api/v1/settings/mattermost").status_code == 403
        assert (
            client.post(
                "/api/v1/settings/mattermost/verify",
                headers=member_headers,
                json={
                    "server_url": "https://mattermost.web.cern.ch",
                    "credential": "must-not-be-used",
                },
            ).status_code
            == 403
        )


def test_brew_transitions_create_and_cancel_durable_mattermost_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "delivery_worker", inactive_mattermost_worker)
    monkeypatch.setattr(
        mattermost_module.MattermostClient,
        "verify_pat",
        lambda _client: mattermost_verification(),
    )
    with build_client(tmp_path, mattermost_secret_key=Fernet.generate_key().decode()) as client:
        _session, headers = bootstrap(client)
        configured = client.put(
            "/api/v1/settings/mattermost",
            headers=headers,
            json=mattermost_settings_payload(),
        )
        assert configured.status_code == 200, configured.text
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit @channel", "name": "Kenya @all"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        member = client.post(
            "/api/v1/people",
            headers=headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        client.put(
            f"/api/v1/people/{member['id']}",
            headers=headers,
            json={"pin_change_required": False},
        )
        brew_input = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }
        create_headers = {**headers, "Idempotency-Key": "mattermost-brew-create"}
        created = client.post("/api/v1/brews", headers=create_headers, json=brew_input).json()
        replayed = client.post("/api/v1/brews", headers=create_headers, json=brew_input).json()
        assert replayed["id"] == created["id"]

        member_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        joined = client.post(
            f"/api/v1/brews/{created['id']}/join",
            headers={"X-CSRF-Token": member_login["csrf_token"]},
            json={},
        ).json()
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        edited_response = client.put(
            f"/api/v1/brews/{created['id']}",
            headers=headers,
            json={**brew_input, "temperature_c": 93, "revision": joined["revision"]},
        )
        assert edited_response.status_code == 200, edited_response.text
        edited = edited_response.json()

        finalized_response = client.post(
            f"/api/v1/brews/{created['id']}/finalize",
            headers=headers,
            json={"total_brew_time_s": 180, "revision": edited["revision"]},
        )
        assert finalized_response.status_code == 200, finalized_response.text
        finalized = finalized_response.json()
        correction = client.put(
            f"/api/v1/brews/{created['id']}/correction",
            headers=headers,
            json={
                "revision": client.get(f"/api/v1/brews/{created['id']}").json()["revision"],
                **brew_input,
                "temperature_c": 92,
                "total_brew_time_s": 181,
            },
        )
        assert correction.status_code == 200, correction.text

        cancelled = client.post(
            "/api/v1/brews",
            headers={**headers, "Idempotency-Key": "mattermost-cancel-create"},
            json=brew_input,
        ).json()
        cancel_response = client.post(
            f"/api/v1/brews/{cancelled['id']}/cancel",
            headers=headers,
            json={"revision": cancelled["revision"]},
        )
        assert cancel_response.status_code == 200

        void_candidate = client.post(
            "/api/v1/brews",
            headers={**headers, "Idempotency-Key": "mattermost-void-create"},
            json=brew_input,
        ).json()
        completed_for_void = client.post(
            f"/api/v1/brews/{void_candidate['id']}/finalize",
            headers=headers,
            json={"total_brew_time_s": 175, "revision": void_candidate["revision"]},
        ).json()
        void_response = client.post(
            f"/api/v1/brews/{void_candidate['id']}/void",
            headers=headers,
            json={"revision": completed_for_void["revision"]},
        )
        assert void_response.status_code == 200

        cloned = client.post(f"/api/v1/brews/{finalized['id']}/clone", headers=headers, json={})
        assert cloned.status_code == 200, cloned.text

        with client.app.state.session_factory() as db:
            notifications = list(
                db.scalars(select(MattermostNotification).order_by(MattermostNotification.id))
            )
            assert [item.event_type for item in notifications] == [
                "brew_started",
                "ready_to_rate",
                "brew_started",
                "brew_started",
                "ready_to_rate",
                "brew_started",
            ]
            assert [item.state for item in notifications] == [
                "pending",
                "pending",
                "cancelled",
                "cancelled",
                "cancelled",
                "pending",
            ]
            started_message = notifications[0].message
            ready_message = notifications[1].message
            assert started_message.startswith("@channel\n")
            assert started_message.count("@channel") == 1
            assert "@\u200bchannel" in started_message
            assert f"/brews/{created['id']}" in started_message
            assert "@channel" not in ready_message
            assert "Ada, Grace" in ready_message
            assert f"/rate/{finalized['rating_token']}" in ready_message
