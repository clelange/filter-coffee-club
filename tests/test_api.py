from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.models import Profile
from app.security import _attempts
from fastapi.testclient import TestClient


def build_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        frontend_dir=tmp_path / "missing-frontend",
        public_base_url="http://fcc.test",
    )
    return TestClient(create_app(settings))


def bootstrap(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/bootstrap", json={"display_name": "Ada", "pin": "1234"})
    assert response.status_code == 200, response.text
    session = response.json()
    return session, {"X-CSRF-Token": session["csrf_token"]}


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

        grinders = client.get("/api/v1/grinders").json()
        assert grinders[0]["manufacturer"] == "Comandante"
        assert grinders[0]["model"] == "C40"
        presets = client.get("/api/v1/presets").json()
        assert len(presets) == 7
        tags = client.get("/api/v1/flavor-tags").json()
        assert any(item["name"] == "Fruity" and item["parent_id"] is None for item in tags)

        invalid_grinder = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
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
        invalid_preset["grinder_ranges"] = [
            {
                **presets[0]["grinder_ranges"][0],
                "setting_min": 28.5,
            }
        ]
        preset_response = client.put(
            f"/api/v1/presets/{presets[0]['id']}",
            headers=headers,
            json=invalid_preset,
        )
        assert preset_response.status_code == 422
        assert preset_response.json()["detail"] == "Preset click ranges must use whole numbers"


def test_brew_qr_and_rating_visibility(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        member = client.post(
            "/api/v1/people",
            headers=headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "PSI Roasters", "name": "Collider Blend"},
        ).json()
        dripper = client.post(
            "/api/v1/drippers",
            headers=headers,
            json={"manufacturer": "Hario", "model": "V60", "notes": None},
        ).json()
        brew_filter = client.post(
            "/api/v1/filters",
            headers=headers,
            json={"name": "V60 paper 02", "notes": None},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        fractional_clicks = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30.5,
            },
        )
        assert fractional_clicks.status_code == 422
        assert fractional_clicks.json()["detail"] == "Grinder click settings must be whole numbers"

        brew = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dripper_id": dripper["id"],
                "filter_id": brew_filter["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30,
                "servings": 2,
                "target_flow_g_s": 4.5,
                "bloom_water_g": 45,
                "bloom_time_s": 30,
                "pour_count": 3,
            },
        ).json()
        assert brew["ratio"] == 16

        abandoned = client.post(f"/api/v1/brews/{brew['id']}/clone", headers=headers).json()
        cancelled = client.post(f"/api/v1/brews/{abandoned['id']}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        repeat_cancel = client.post(f"/api/v1/brews/{abandoned['id']}/cancel", headers=headers)
        assert repeat_cancel.status_code == 409
        assert repeat_cancel.json()["detail"] == "Only draft brews can be cancelled"
        assert (
            client.post(f"/api/v1/brews/{abandoned['id']}/void", headers=headers).status_code == 409
        )

        finalized_response = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=headers,
            json={"total_brew_time_s": 180, "water_g": 242},
        )
        assert finalized_response.status_code == 200, finalized_response.text
        finalized = finalized_response.json()
        assert finalized["status"] == "completed"
        assert finalized["rating_token"]
        assert finalized["overall_throughput_g_s"] == 1.34
        cancel_completed = client.post(f"/api/v1/brews/{brew['id']}/cancel", headers=headers)
        assert cancel_completed.status_code == 409
        assert cancel_completed.json()["detail"] == "Only draft brews can be cancelled"

        link = client.get(f"/api/v1/rating-links/{finalized['rating_token']}").json()
        assert link["active"] is True
        qr = client.get(f"/api/v1/brews/{brew['id']}/qr.svg")
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")
        assert b'width="328"' in qr.content
        assert client.get("/api/v1/settings").json()["public_base_url"] == "http://fcc.test"

        client.post("/api/v1/auth/logout", headers=headers)
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get(f"/api/v1/rating-links/{finalized['rating_token']}").status_code == 200
        assert client.get("/api/v1/rating-links/not-a-token").status_code == 404
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        assert login.status_code == 200
        assert login.json()["profile"]["pin_change_required"] is True
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        pin_change = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "5678", "new_pin": "6789"},
        )
        assert pin_change.status_code == 204
        assert client.get("/api/v1/auth/me").json()["profile"]["pin_change_required"] is False
        updated_grinder = client.put(
            f"/api/v1/grinders/{grinder['id']}",
            headers=member_headers,
            json={
                "manufacturer": grinder["manufacturer"],
                "model": grinder["model"],
                "setting_unit": grinder["setting_unit"],
                "setting_step": grinder["setting_step"],
                "soft_min": grinder["soft_min"],
                "soft_max": grinder["soft_max"],
                "guidance": "Member-corrected guidance",
            },
        )
        assert updated_grinder.status_code == 200
        assert (
            client.post(
                f"/api/v1/grinders/{grinder['id']}/archive", headers=member_headers
            ).status_code
            == 403
        )
        assert (
            client.post(f"/api/v1/brews/{brew['id']}/void", headers=member_headers).status_code
            == 403
        )

        hidden = client.get(f"/api/v1/brews/{brew['id']}/ratings").json()
        assert hidden == {
            "can_view": False,
            "own_rating": None,
            "ratings": [],
            "count": 0,
            "averages": {},
            "flavor_counts": {},
        }
        fruity = next(
            item
            for item in client.get("/api/v1/flavor-tags").json()
            if item["name"] == "Fruity" and item["parent_id"] is None
        )
        too_many_tags = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 8,
                "acidity": 3,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [
                    item["id"] for item in client.get("/api/v1/flavor-tags").json()[:6]
                ],
            },
        )
        assert too_many_tags.status_code == 422
        rated = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 8,
                "acidity": 3,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [fruity["id"]],
            },
        )
        assert rated.status_code == 200, rated.text
        assert rated.json()["can_view"] is True
        assert rated.json()["averages"]["liking"] == 8
        updated = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 9,
                "acidity": 2,
                "bitterness": 1,
                "sweetness": 5,
                "body": 3,
                "flavor_tag_ids": [],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["count"] == 1
        assert updated.json()["averages"]["liking"] == 9

        client.post("/api/v1/auth/logout", headers=member_headers)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        corrected = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers={"X-CSRF-Token": admin_login["csrf_token"]},
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dripper_id": dripper["id"],
                "filter_id": brew_filter["id"],
                "source_preset_id": None,
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 93,
                "grinder_setting": 31,
                "servings": 2,
                "target_flow_g_s": 4.5,
                "bloom_water_g": 45,
                "bloom_time_s": 30,
                "pour_count": 3,
                "technique_note": None,
                "total_brew_time_s": 181,
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["temperature_c"] == 93
        voided = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers={"X-CSRF-Token": admin_login["csrf_token"]},
        )
        assert voided.status_code == 200
        repeat_void = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers={"X-CSRF-Token": admin_login["csrf_token"]},
        )
        assert repeat_void.status_code == 409
        assert repeat_void.json()["detail"] == "Only completed brews can be voided"
        inactive = client.get(f"/api/v1/rating-links/{finalized['rating_token']}").json()
        assert inactive == {"active": False, "brew": None}


def test_export_omits_auth_secrets(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        response = client.get("/api/v1/exports/json")
        assert response.status_code == 200
        body = response.text
        assert "pin_hash" not in body
        assert "rating_token" not in body
        csv_response = client.get("/api/v1/exports/csv")
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(csv_response.content)) as archive:
            combined = "".join(archive.read(name).decode() for name in archive.namelist())
        assert "pin_hash" not in combined
        assert "rating_token" not in combined


def test_kiosk_session_is_fixed_and_logout_revokes_it(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        client.post("/api/v1/auth/logout", headers=headers)
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "kiosk"},
        )
        assert login.status_code == 200
        session = login.json()
        remaining_hours = (
            datetime.fromisoformat(session["expires_at"]) - datetime.now(UTC)
        ).total_seconds() / 3600
        assert 3.99 < remaining_hours <= 4
        kiosk_headers = {"X-CSRF-Token": session["csrf_token"]}
        assert client.post("/api/v1/auth/logout", headers=kiosk_headers).status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


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


def test_failed_logins_are_rate_limited(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        bootstrap(client)
        try:
            for _ in range(8):
                response = client.post(
                    "/api/v1/auth/login",
                    json={"profile_id": 1, "pin": "9999", "device_mode": "personal"},
                )
                assert response.status_code == 401
            blocked = client.post(
                "/api/v1/auth/login",
                json={"profile_id": 1, "pin": "9999", "device_mode": "personal"},
            )
            assert blocked.status_code == 429
        finally:
            _attempts.clear()
