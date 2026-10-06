from __future__ import annotations

from pathlib import Path

import pytest
from app import main as main_module
from app.demo import DEMO_PROFILE_NAMES, _write_attempts
from app.models import (
    Profile,
)

from tests.api_helpers import build_demo_client, image_upload, mattermost_settings_payload


def test_demo_mode_seeds_examples_and_protects_reset_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden_mattermost_worker(*_args: object) -> None:
        raise AssertionError("Mattermost worker must not start in demo mode")

    monkeypatch.setattr(main_module, "delivery_worker", forbidden_mattermost_worker)
    try:
        with build_demo_client(tmp_path) as client:
            assert client.get("/api/v1/auth/bootstrap-status").json() == {"required": False}
            assert (
                client.post(
                    "/api/v1/auth/bootstrap",
                    json={"display_name": "Takeover", "pin": "9999"},
                ).status_code
                == 403
            )

            profiles = client.get("/api/v1/auth/profiles").json()
            assert [item["display_name"] for item in profiles] == sorted(DEMO_PROFILE_NAMES)
            coffees = client.get("/api/v1/coffees").json()
            assert len(coffees) == 4
            assert all(item["photo_path"] for item in coffees)
            demo_photo = client.get(coffees[0]["photo_path"])
            assert demo_photo.status_code == 200
            assert demo_photo.headers["content-type"] == "image/webp"
            grinders = client.get("/api/v1/grinders").json()
            drippers = client.get("/api/v1/drippers").json()
            filters = client.get("/api/v1/filters").json()
            assert grinders[0]["photo_path"]
            assert sum(item["photo_path"] is not None for item in drippers) == 1
            assert sum(item["photo_path"] is not None for item in filters) == 1
            assert len(client.get("/api/v1/brews").json()) == 12

            settings = client.get("/api/v1/settings").json()
            assert settings["demo_mode"] is True
            assert settings["demo_pin"] == "1234"
            assert settings["demo_profile_names"] == list(DEMO_PROFILE_NAMES)
            assert settings["public_base_url"] == "http://demo.fcc.test"
            assert "Do not enter personal" in settings["demo_notice"]

            admin = next(item for item in profiles if item["display_name"] == "Demo Admin")
            login = client.post(
                "/api/v1/auth/login",
                json={"profile_id": admin["id"], "pin": "1234", "device_mode": "personal"},
            )
            assert login.status_code == 200
            headers = {"X-CSRF-Token": login.json()["csrf_token"]}
            mattermost_settings = client.get("/api/v1/settings/mattermost").json()
            assert mattermost_settings["enabled"] is False
            assert (
                client.put(
                    "/api/v1/settings/mattermost",
                    headers=headers,
                    json=mattermost_settings_payload(),
                ).status_code
                == 403
            )
            analytics = client.get("/api/v1/analytics").json()
            assert analytics["counts"] == {"brews": 12, "ratings": 36, "coffees": 4}

            pin_change = client.post(
                "/api/v1/auth/pin",
                headers=headers,
                json={"current_pin": "1234", "new_pin": "5678"},
            )
            assert pin_change.status_code == 403
            assert pin_change.json()["detail"] == "Demo profile credentials are fixed"

            profile_change = client.put(
                f"/api/v1/people/{admin['id']}",
                headers=headers,
                json={"active": False},
            )
            assert profile_change.status_code == 403

            seeded_coffee_change = client.put(
                f"/api/v1/coffees/{coffees[0]['id']}",
                headers=headers,
                json={"roaster": "Vandal", "name": "Changed"},
            )
            assert seeded_coffee_change.status_code == 403
            assert seeded_coffee_change.json()["detail"].startswith(
                "Seeded demo records are read-only"
            )

            new_coffee = client.post(
                "/api/v1/coffees",
                headers=headers,
                json={"roaster": "Visitor", "name": "Experiment"},
            ).json()
            editable_coffee = client.put(
                f"/api/v1/coffees/{new_coffee['id']}",
                headers=headers,
                json={"roaster": "Visitor", "name": "Edited experiment"},
            )
            assert editable_coffee.status_code == 200

            settings_update = client.put(
                "/api/v1/settings",
                headers=headers,
                json={
                    "app_name": settings["app_name"],
                    "subtitle": settings["subtitle"],
                    "public_base_url": "https://vandal.invalid",
                    "color_cream": settings["color_cream"],
                    "color_surface": settings["color_surface"],
                    "color_ink": settings["color_ink"],
                    "color_coffee": settings["color_coffee"],
                    "color_cyan": settings["color_cyan"],
                    "color_amber": settings["color_amber"],
                    "max_active_brews": settings["max_active_brews"],
                },
            )
            assert settings_update.status_code == 403
            assert settings_update.json()["detail"] == "Branding is read-only in demo mode"
            assert (
                client.get("/api/v1/settings").json()["public_base_url"] == "http://demo.fcc.test"
            )

            upload = client.post(
                "/api/v1/settings/logo",
                headers=headers,
                files={"logo": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload.status_code == 403
            brewing_upload = client.post(
                "/api/v1/settings/brewing-logo",
                headers=headers,
                files={"logo": ("brewing.png", image_upload(size=(20, 20)), "image/png")},
            )
            assert brewing_upload.status_code == 403
            assert (
                client.delete("/api/v1/settings/brewing-logo", headers=headers).status_code == 403
            )
            assert (
                client.post("/api/v1/settings/brewing-logo/default", headers=headers).status_code
                == 403
            )
            photo_upload = client.put(
                f"/api/v1/coffees/{coffees[0]['id']}/photo",
                headers=headers,
                files={"photo": ("photo.png", image_upload(), "image/png")},
            )
            assert photo_upload.status_code == 403
            assert photo_upload.json()["detail"] == "Photo changes are disabled in demo mode"
            photo_framing = client.patch(
                f"/api/v1/coffees/{coffees[0]['id']}/photo",
                headers=headers,
                json={"photo_framing": None},
            )
            assert photo_framing.status_code == 403
            assert photo_framing.json()["detail"] == "Photo changes are disabled in demo mode"

        with build_demo_client(tmp_path) as client:
            assert len(client.get("/api/v1/brews").json()) == 12
    finally:
        _write_attempts.clear()


def test_shared_demo_profiles_are_not_persistently_blocked(tmp_path: Path) -> None:
    with build_demo_client(tmp_path) as client:
        profile = next(
            item
            for item in client.get("/api/v1/auth/profiles").json()
            if item["display_name"] == "Demo Admin"
        )
        payload = {"profile_id": profile["id"], "pin": "9999", "device_mode": "personal"}
        for _ in range(10):
            response = client.post("/api/v1/auth/login", json=payload)
            assert response.status_code == 401
        with client.app.state.session_factory() as db:
            stored = db.get(Profile, profile["id"])
            assert stored is not None
            assert stored.failed_login_attempts == 0
            assert stored.login_blocked_until is None
        assert (
            client.post(
                "/api/v1/auth/login",
                json={
                    "profile_id": profile["id"],
                    "pin": "1234",
                    "device_mode": "personal",
                },
            ).status_code
            == 200
        )
