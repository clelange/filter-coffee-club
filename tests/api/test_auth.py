from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from app.models import (
    Profile,
)
from app.routers import auth as auth_module
from sqlalchemy import select

from tests.api_helpers import bootstrap, build_client


def test_bootstrap_seeds_and_personal_session(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        assert client.get("/api/v1/auth/bootstrap-status").json() == {"required": True}
        session, headers = bootstrap(client)
        assert session["profile"]["role"] == "admin"
        assert session["device_mode"] == "personal"
        assert client.get("/api/v1/auth/bootstrap-status").json() == {"required": False}
        expires_at = datetime.fromisoformat(session["expires_at"])
        remaining_hours = (expires_at - datetime.now(UTC)).total_seconds() / 3600
        assert 83.99 < remaining_hours <= 84
        with client.app.state.session_factory() as db:
            assert db.get(Profile, 1).pin_hash.startswith("$argon2")
        public_profile = client.get("/api/v1/auth/profiles").json()[0]
        assert set(public_profile) == {"id", "display_name"}

        grinders = client.get("/api/v1/grinders").json()
        assert grinders[0]["manufacturer"] == "Comandante"
        assert grinders[0]["model"] == "C40"
        assert grinders[0]["definition_key"] == "comandante_c40"
        assert [item["key"] for item in client.get("/api/v1/grinder-definitions").json()] == [
            "comandante_c40",
            "kingrinder_k6",
            "custom",
        ]
        presets = client.get("/api/v1/presets").json()
        assert len(presets) == 7
        tags = client.get("/api/v1/flavor-tags").json()
        assert any(item["name"] == "Fruity" and item["parent_id"] is None for item in tags)

        invalid_grinder = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Test",
                "model": "Fractional Clicks",
                "setting_unit": "clicks",
                "setting_step": 0.5,
                "soft_min": 0,
                "soft_max": 50,
            },
        )
        assert invalid_grinder.status_code == 422

        invalid_preset = {
            key: value for key, value in presets[0].items() if key not in {"id", "grinder_ranges"}
        }
        invalid_preset["reference_grinder_range"] = {
            "setting_min": 28.5,
            "setting_max": 34,
        }
        invalid_preset["custom_grinder_ranges"] = []
        preset_response = client.put(
            f"/api/v1/presets/{presets[0]['id']}",
            headers=headers,
            json=invalid_preset,
        )
        assert preset_response.status_code == 422

        created_preset = client.post(
            "/api/v1/presets",
            headers=headers,
            json={
                "name": "Club balanced",
                "ratio": 16.5,
                "temperature_min_c": 92,
                "temperature_max_c": 95,
                "active": True,
                "sort_order": 8,
                "reference_grinder_range": {"setting_min": 24, "setting_max": 28},
                "custom_grinder_ranges": [],
            },
        )
        assert created_preset.status_code == 200
        assert created_preset.json()["name"] == "Club balanced"
        assert created_preset.json()["grinder_ranges"] == [
            {
                "grinder_id": grinders[0]["id"],
                "setting_min": 24.0,
                "setting_max": 28.0,
                "source": "reference",
            }
        ]
        assert len(client.get("/api/v1/presets").json()) == 8


def test_concurrent_bootstrap_creates_exactly_one_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        barrier = Barrier(2)
        original_hash_pin = auth_module.hash_pin

        def synchronized_hash_pin(pin: str) -> str:
            result = original_hash_pin(pin)
            barrier.wait(timeout=10)
            return result

        monkeypatch.setattr(auth_module, "hash_pin", synchronized_hash_pin)

        def create_administrator(item: tuple[str, str]) -> tuple[int, dict]:
            name, pin = item
            response = client.post(
                "/api/v1/auth/bootstrap",
                json={"display_name": name, "pin": pin, "device_mode": "personal"},
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    create_administrator,
                    [("Ada", "1234"), ("Grace", "5678")],
                )
            )

        assert sorted(status for status, _body in results) == [200, 409]
        with client.app.state.session_factory() as db:
            administrators = list(
                db.scalars(select(Profile).where(Profile.role == "admin", Profile.active.is_(True)))
            )
        assert len(administrators) == 1


def test_new_profiles_must_replace_temporary_pin_and_admin_can_toggle_requirement(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        member_response = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        )
        assert member_response.status_code == 200
        member = member_response.json()
        assert member["pin_change_required"] is True

        assert client.post("/api/v1/auth/logout", headers=admin_headers).status_code == 204
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        assert login.status_code == 200
        assert login.json()["profile"]["pin_change_required"] is True
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}

        blocked = client.post(
            "/api/v1/coffees",
            headers=member_headers,
            json={"roaster": "PSI Roasters", "name": "Blocked Blend"},
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "PIN change required"

        wrong_current = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "9999", "new_pin": "6789"},
        )
        assert wrong_current.status_code == 400
        assert wrong_current.json()["detail"] == "Current PIN is incorrect"
        unchanged = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "5678", "new_pin": "5678"},
        )
        assert unchanged.status_code == 400

        changed = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "5678", "new_pin": "6789"},
        )
        assert changed.status_code == 204
        assert client.get("/api/v1/auth/me").json()["profile"]["pin_change_required"] is False
        allowed = client.post(
            "/api/v1/coffees",
            headers=member_headers,
            json={"roaster": "PSI Roasters", "name": "Allowed Blend"},
        )
        assert allowed.status_code == 200

        assert client.post("/api/v1/auth/logout", headers=member_headers).status_code == 204
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
            ).status_code
            == 401
        )
        relogin = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "6789", "device_mode": "personal"},
        )
        assert relogin.status_code == 200
        relogin_headers = {"X-CSRF-Token": relogin.json()["csrf_token"]}
        assert client.post("/api/v1/auth/logout", headers=relogin_headers).status_code == 204

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        required = client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"pin_change_required": True},
        )
        assert required.status_code == 200
        assert required.json()["pin_change_required"] is True
        not_required = client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"pin_change_required": False},
        )
        assert not_required.status_code == 200
        assert not_required.json()["pin_change_required"] is False


def test_failed_logins_use_persistent_progressive_backoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = [datetime(2026, 7, 20, 12, tzinfo=UTC)]
    monkeypatch.setattr("app.security.utcnow", lambda: current[0])

    with build_client(tmp_path) as client:
        bootstrap(client)
        payload = {"profile_id": 1, "pin": "9999", "device_mode": "personal"}
        for _ in range(2):
            response = client.post("/api/v1/auth/login", json=payload)
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid profile or PIN"

        blocked = client.post("/api/v1/auth/login", json=payload)
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "30"
        assert blocked.json()["detail"] == "Too many failed attempts. Try again shortly."

        correct_while_blocked = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        assert correct_while_blocked.status_code == 429
        assert correct_while_blocked.headers["Retry-After"] == "30"

        previous_delay = 30
        for expected_delay in (60, 120, 240, 480, 900, 900):
            current[0] += timedelta(seconds=previous_delay)
            blocked = client.post("/api/v1/auth/login", json=payload)
            assert blocked.status_code == 429
            assert blocked.headers["Retry-After"] == str(expected_delay)
            previous_delay = expected_delay

        current[0] += timedelta(seconds=previous_delay)
        success = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        assert success.status_code == 200
        with client.app.state.session_factory() as db:
            profile = db.get(Profile, 1)
            assert profile is not None
            assert profile.failed_login_attempts == 0
            assert profile.last_failed_login_at is None
            assert profile.login_blocked_until is None

        client.post("/api/v1/auth/login", json=payload)
        client.post("/api/v1/auth/login", json=payload)
        current[0] += timedelta(hours=24)
        after_quiet_period = client.post("/api/v1/auth/login", json=payload)
        assert after_quiet_period.status_code == 401
        with client.app.state.session_factory() as db:
            profile = db.get(Profile, 1)
            assert profile is not None
            assert profile.failed_login_attempts == 1
            assert profile.login_blocked_until is None

        login_responses = client.get("/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"][
            "responses"
        ]
        assert "Retry-After" in login_responses["429"]["headers"]


def test_login_backoff_survives_application_restart(tmp_path: Path) -> None:
    payload = {"profile_id": 1, "pin": "9999", "device_mode": "personal"}
    with build_client(tmp_path) as client:
        bootstrap(client)
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401
        assert client.post("/api/v1/auth/login", json=payload).status_code == 429

    with build_client(tmp_path) as restarted_client:
        blocked = restarted_client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        assert blocked.status_code == 429
        assert 1 <= int(blocked.headers["Retry-After"]) <= 30


def test_concurrent_login_failures_are_serialized_per_profile(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        bootstrap(client)
        payload = {"profile_id": 1, "pin": "9999", "device_mode": "personal"}

        def attempt_login(_attempt: int) -> int:
            return client.post("/api/v1/auth/login", json=payload).status_code

        with ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(attempt_login, range(8)))

        assert sorted(statuses) == [401, 401, 429, 429, 429, 429, 429, 429]
        with client.app.state.session_factory() as db:
            profile = db.get(Profile, 1)
            assert profile is not None
            assert profile.failed_login_attempts == 3


def test_login_backoff_is_per_profile_and_pin_management_clears_it(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        wrong_member = {
            "profile_id": member["id"],
            "pin": "9999",
            "device_mode": "personal",
        }
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 429

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        assert admin_login.status_code == 200
        admin_headers = {"X-CSRF-Token": admin_login.json()["csrf_token"]}
        reset = client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"pin": "1357"},
        )
        assert reset.status_code == 200

        member_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "1357", "device_mode": "personal"},
        )
        assert member_login.status_code == 200
        member_headers = {"X-CSRF-Token": member_login.json()["csrf_token"]}

        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 429
        self_reset = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "1357", "new_pin": "2468"},
        )
        assert self_reset.status_code == 204
        assert (
            client.post(
                "/api/v1/auth/login",
                json={
                    "profile_id": member["id"],
                    "pin": "2468",
                    "device_mode": "personal",
                },
            ).status_code
            == 200
        )

        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 401
        assert client.post("/api/v1/auth/login", json=wrong_member).status_code == 429
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        assert (
            client.put(
                f"/api/v1/people/{member['id']}",
                headers=admin_headers,
                json={"active": False},
            ).status_code
            == 200
        )
        inactive = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "2468", "device_mode": "personal"},
        )
        missing = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 9999, "pin": "2468", "device_mode": "personal"},
        )
        assert inactive.status_code == missing.status_code == 401
        assert inactive.json() == missing.json() == {"detail": "Invalid profile or PIN"}

        reactivated = client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"active": True},
        )
        assert reactivated.status_code == 200
        assert (
            client.post(
                "/api/v1/auth/login",
                json={
                    "profile_id": member["id"],
                    "pin": "2468",
                    "device_mode": "personal",
                },
            ).status_code
            == 200
        )
