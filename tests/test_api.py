from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

from app import api as api_module
from app.config import Settings
from app.demo import DEMO_PROFILE_NAMES, _write_attempts
from app.main import create_app
from app.models import Profile
from fastapi.testclient import TestClient
from PIL import Image


def build_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        frontend_dir=tmp_path / "missing-frontend",
        public_base_url="http://fcc.test",
        **overrides,
    )
    return TestClient(create_app(settings))


def build_demo_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'demo.sqlite3'}",
        frontend_dir=tmp_path / "missing-frontend",
        public_base_url="http://demo.fcc.test",
        demo_mode=True,
    )
    return TestClient(create_app(settings))


def bootstrap(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/bootstrap", json={"display_name": "Ada", "pin": "1234"})
    assert response.status_code == 200, response.text
    session = response.json()
    return session, {"X-CSRF-Token": session["csrf_token"]}


def image_upload(format_name: str = "PNG", size: tuple[int, int] = (2000, 1000)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#8f4f38").save(output, format=format_name)
    return output.getvalue()


def multipicture_jpeg_upload() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2000, 1000), "#8f4f38").save(
        output,
        format="MPO",
        save_all=True,
        append_images=[Image.new("RGB", (320, 180), "#ffffff")],
    )
    return output.getvalue()


def animated_gif_upload() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (5, 5), "#8f4f38").save(
        output,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (5, 5), "#ffffff")],
        duration=100,
        loop=0,
    )
    return output.getvalue()


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
                "grinder_ranges": [
                    {
                        "grinder_id": grinders[0]["id"],
                        "setting_min": 24,
                        "setting_max": 28,
                    }
                ],
            },
        )
        assert created_preset.status_code == 200
        assert created_preset.json()["name"] == "Club balanced"
        assert len(client.get("/api/v1/presets").json()) == 8


def test_member_directory_visibility_and_account_filtering(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        profiles = {}
        for name, pin in (
            ("Grace", "5678"),
            ("Linus", "6789"),
            ("Inactive", "7890"),
            ("Pending", "8901"),
        ):
            profiles[name] = client.post(
                "/api/v1/people",
                headers=admin_headers,
                json={"display_name": name, "pin": pin, "role": "member"},
            ).json()
        for name in ("Grace", "Linus"):
            assert (
                client.put(
                    f"/api/v1/people/{profiles[name]['id']}",
                    headers=admin_headers,
                    json={"pin_change_required": False},
                ).status_code
                == 200
            )
        assert (
            client.put(
                f"/api/v1/people/{profiles['Inactive']['id']}",
                headers=admin_headers,
                json={"active": False},
            ).status_code
            == 200
        )

        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Directory", "name": "Shared Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        def completed_brew(setting: int) -> dict:
            brew = client.post(
                "/api/v1/brews",
                headers=admin_headers,
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 94,
                    "grinder_setting": setting,
                },
            ).json()
            return client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=admin_headers,
                json={"total_brew_time_s": 180},
            ).json()

        shared_brew = completed_brew(20)
        grace_brew = completed_brew(21)
        linus_brew = completed_brew(22)
        voided_brew = completed_brew(23)
        rating_payload = {
            "liking": 7,
            "acidity": 3,
            "bitterness": 2,
            "sweetness": 4,
            "body": 3,
            "flavor_tag_ids": [],
        }
        for brew in (shared_brew, grace_brew, linus_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=admin_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )

        def login(name: str, pin: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "profile_id": profiles[name]["id"],
                    "pin": pin,
                    "device_mode": "personal",
                },
            )
            assert response.status_code == 200, response.text
            return {"X-CSRF-Token": response.json()["csrf_token"]}

        grace_headers = login("Grace", "5678")
        for brew in (shared_brew, grace_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=grace_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )
        linus_headers = login("Linus", "6789")
        for brew in (shared_brew, linus_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=linus_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        assert (
            client.post(
                f"/api/v1/brews/{voided_brew['id']}/void", headers=admin_headers
            ).status_code
            == 200
        )

        login("Grace", "5678")
        member_directory = client.get("/api/v1/profiles")
        assert member_directory.status_code == 200
        member_items = member_directory.json()
        assert [item["display_name"] for item in member_items] == [
            "Ada",
            "Grace",
            "Linus",
            "Pending",
        ]
        assert all(
            set(item)
            == {
                "id",
                "display_name",
                "is_self",
                "is_complete_history",
                "rating_count",
            }
            for item in member_items
        )
        member_by_name = {item["display_name"]: item for item in member_items}
        assert member_by_name["Grace"] == {
            "id": profiles["Grace"]["id"],
            "display_name": "Grace",
            "is_self": True,
            "is_complete_history": True,
            "rating_count": 2,
        }
        assert member_by_name["Ada"]["rating_count"] == 2
        assert member_by_name["Linus"]["rating_count"] == 1
        assert member_by_name["Linus"]["is_complete_history"] is False
        assert member_by_name["Pending"]["rating_count"] == 0

        client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        admin_items = client.get("/api/v1/profiles").json()
        admin_by_name = {item["display_name"]: item for item in admin_items}
        assert all(item["is_complete_history"] for item in admin_items)
        assert admin_by_name["Ada"]["rating_count"] == 3
        assert admin_by_name["Grace"]["rating_count"] == 2
        assert admin_by_name["Linus"]["rating_count"] == 2

        login("Pending", "8901")
        assert client.get("/api/v1/profiles").status_code == 403
        pending_session = client.get("/api/v1/auth/me").json()
        pending_headers = {"X-CSRF-Token": pending_session["csrf_token"]}
        assert client.post("/api/v1/auth/logout", headers=pending_headers).status_code == 204
        assert client.get("/api/v1/profiles").status_code == 401


def test_demo_mode_seeds_examples_and_protects_reset_anchors(tmp_path: Path) -> None:
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
            photo_upload = client.put(
                f"/api/v1/coffees/{coffees[0]['id']}/photo",
                headers=headers,
                files={"photo": ("photo.png", image_upload(), "image/png")},
            )
            assert photo_upload.status_code == 403
            assert photo_upload.json()["detail"] == "Photo changes are disabled in demo mode"

        with build_demo_client(tmp_path) as client:
            assert len(client.get("/api/v1/brews").json()) == 12
    finally:
        _write_attempts.clear()


def test_catalog_photos_upload_replace_remove_and_permissions(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "PSI Roasters", "name": "Photo Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        dripper = client.post(
            "/api/v1/drippers",
            headers=headers,
            json={"manufacturer": "Demo", "model": "Cone"},
        ).json()
        brew_filter = client.post(
            "/api/v1/filters",
            headers=headers,
            json={"name": "Demo paper"},
        ).json()

        targets = [
            ("coffees", coffee),
            ("grinders", grinder),
            ("drippers", dripper),
            ("filters", brew_filter),
        ]
        for resource, item in targets:
            response = client.put(
                f"/api/v1/{resource}/{item['id']}/photo",
                headers=headers,
                files={"photo": ("photo.png", image_upload(), "image/png")},
            )
            assert response.status_code == 200, response.text
            path = response.json()["photo_path"]
            assert path.startswith("/uploads/catalog/photo-")
            stored = client.get(path)
            assert stored.status_code == 200
            assert stored.headers["content-type"] == "image/webp"
            with Image.open(io.BytesIO(stored.content)) as image:
                assert image.format == "WEBP"
                assert image.size == (1600, 800)
                assert not image.getexif()

        coffee_path = client.get(f"/api/v1/coffees/{coffee['id']}").json()["photo_path"]
        replacement = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            files={"photo": ("replacement.jpg", image_upload("JPEG", (400, 600)), "image/jpeg")},
        )
        assert replacement.status_code == 200
        replacement_path = replacement.json()["photo_path"]
        assert replacement_path != coffee_path
        assert client.get(coffee_path).status_code == 404

        heic_upload = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            files={"photo": ("iphone.heic", image_upload("HEIF", (3024, 4032)), "image/heic")},
        )
        assert heic_upload.status_code == 200, heic_upload.text
        heic_path = heic_upload.json()["photo_path"]
        with Image.open(io.BytesIO(client.get(heic_path).content)) as image:
            assert image.format == "WEBP"
            assert image.size == (1200, 1600)

        clone = client.post(
            f"/api/v1/coffees/{coffee['id']}/clone",
            headers=headers,
            json={},
        )
        assert clone.status_code == 200
        assert clone.json()["photo_path"] is None

        removed = client.delete(f"/api/v1/coffees/{coffee['id']}/photo", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["photo_path"] is None
        assert client.get(replacement_path).status_code == 404

        ios_converted_upload = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            files={"photo": ("iphone.heic", image_upload("JPEG"), "image/heic")},
        )
        assert ios_converted_upload.status_code == 200, ios_converted_upload.text
        ios_converted_path = ios_converted_upload.json()["photo_path"]
        with Image.open(io.BytesIO(client.get(ios_converted_path).content)) as image:
            assert image.format == "WEBP"
            assert image.size == (1600, 800)

        multipicture_upload = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            files={"photo": ("iphone.jpg", multipicture_jpeg_upload(), "image/jpeg")},
        )
        assert multipicture_upload.status_code == 200, multipicture_upload.text
        multipicture_path = multipicture_upload.json()["photo_path"]
        with Image.open(io.BytesIO(client.get(multipicture_path).content)) as image:
            assert image.format == "WEBP"
            assert image.size == (1600, 800)

        client.post("/api/v1/auth/logout", headers=headers)
        kiosk_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "kiosk"},
        ).json()
        kiosk_upload = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers={"X-CSRF-Token": kiosk_login["csrf_token"]},
            files={"photo": ("photo.png", image_upload(), "image/png")},
        )
        assert kiosk_upload.status_code == 403
        assert kiosk_upload.json()["detail"] == "Photo changes are unavailable in kiosk mode"


def test_catalog_photo_validation_limits(tmp_path: Path) -> None:
    size_path = tmp_path / "size-limit"
    with build_client(size_path, max_catalog_photo_bytes=32) as client:
        _session, headers = bootstrap(client)
        oversized = client.put(
            "/api/v1/grinders/1/photo",
            headers=headers,
            files={"photo": ("photo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"] == "Photo exceeds 32 bytes"

    pixel_path = tmp_path / "pixel-limit"
    with build_client(pixel_path, max_catalog_photo_pixels=100) as client:
        _session, headers = bootstrap(client)
        excessive_resolution = client.put(
            "/api/v1/grinders/1/photo",
            headers=headers,
            files={"photo": ("photo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert excessive_resolution.status_code == 413
        assert excessive_resolution.json()["detail"] == "Photo resolution is too large"

        unsupported = client.put(
            "/api/v1/grinders/1/photo",
            headers=headers,
            files={"photo": ("photo.jpg", animated_gif_upload(), "image/jpeg")},
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["detail"] == "Animated photos are not supported"


def test_catalog_usage_insights_and_equipment_detail_reads(tmp_path: Path) -> None:
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
            json={"roaster": "Orbit", "name": "Catalog lot"},
        ).json()
        empty_coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Unused lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        dripper = client.post(
            "/api/v1/drippers",
            headers=headers,
            json={"manufacturer": "Hario", "model": "V60"},
        ).json()
        brew_filter = client.post(
            "/api/v1/filters",
            headers=headers,
            json={"name": "V60 paper 02"},
        ).json()

        assert client.get(f"/api/v1/grinders/{grinder['id']}").status_code == 200
        assert client.get(f"/api/v1/drippers/{dripper['id']}").status_code == 200
        assert client.get(f"/api/v1/filters/{brew_filter['id']}").status_code == 200
        assert client.get("/api/v1/grinders/99999").status_code == 404
        assert client.get("/api/v1/drippers/99999").status_code == 404
        assert client.get("/api/v1/filters/99999").status_code == 404

        completed: list[dict] = []
        temperatures: list[int] = []
        throughputs: list[float] = []
        for index in range(13):
            temperature = 90 + (index % 5)
            total_time = 180 + index
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
                    "temperature_c": temperature,
                    "grinder_setting": 20 + index,
                },
            ).json()
            finalized = client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": total_time},
            )
            assert finalized.status_code == 200, finalized.text
            completed.append(finalized.json())
            temperatures.append(temperature)
            throughputs.append(240 / total_time)

        draft = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        cancelled = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        assert (
            client.post(f"/api/v1/brews/{cancelled['id']}/cancel", headers=headers).status_code
            == 200
        )
        voided = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        assert (
            client.post(
                f"/api/v1/brews/{voided['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": 200},
            ).status_code
            == 200
        )
        assert client.post(f"/api/v1/brews/{voided['id']}/void", headers=headers).status_code == 200
        assert draft["status"] == "draft"

        for brew, liking in ((completed[-1], 8), (completed[-2], 6)):
            rated = client.post(
                f"/api/v1/brews/{brew['id']}/ratings",
                headers=headers,
                json={
                    "liking": liking,
                    "acidity": 3,
                    "bitterness": 2,
                    "sweetness": 4,
                    "body": 3,
                    "flavor_tag_ids": [],
                },
            )
            assert rated.status_code == 200, rated.text

        usage = client.get("/api/v1/catalog/usage").json()["items"]
        for kind, item_id in (
            ("coffee", coffee["id"]),
            ("grinder", grinder["id"]),
            ("dripper", dripper["id"]),
            ("filter", brew_filter["id"]),
        ):
            item_usage = next(
                item for item in usage if item["kind"] == kind and item["item_id"] == item_id
            )
            assert item_usage["completed_brew_count"] == 13
            assert item_usage["last_completed_at"] is not None

        insights = client.get(f"/api/v1/catalog/coffee/{coffee['id']}/insights").json()
        assert insights["completed_brew_count"] == 13
        assert insights["average_ratio"] == 16
        assert insights["average_temperature_c"] == round(sum(temperatures) / 13, 2)
        assert insights["average_total_brew_time_s"] == 186
        assert insights["average_overall_throughput_g_s"] == round(sum(throughputs) / 13, 2)
        assert insights["observed_grinder_setting_min"] is None
        assert insights["ratings_visible"] is True
        assert insights["rating_count"] == 2
        assert insights["average_liking"] == 7
        assert len(insights["recent_brews"]) == 12
        assert [brew["id"] for brew in insights["recent_brews"]] == [
            brew["id"] for brew in reversed(completed[1:])
        ]
        assert insights["recent_brews"][0]["rating_count"] == 1

        grinder_insights = client.get(
            f"/api/v1/catalog/grinder/{grinder['id']}/insights?limit=1"
        ).json()
        assert grinder_insights["observed_grinder_setting_min"] == 20
        assert grinder_insights["observed_grinder_setting_max"] == 32
        assert len(grinder_insights["recent_brews"]) == 1

        empty = client.get(f"/api/v1/catalog/coffee/{empty_coffee['id']}/insights").json()
        assert empty["completed_brew_count"] == 0
        assert empty["last_completed_at"] is None
        assert empty["recent_brews"] == []
        assert client.get("/api/v1/catalog/coffee/99999/insights").status_code == 404

        archived = client.post(f"/api/v1/drippers/{dripper['id']}/archive", headers=headers)
        assert archived.status_code == 200
        direct_archived = client.get(f"/api/v1/drippers/{dripper['id']}")
        assert direct_archived.status_code == 200
        assert direct_archived.json()["archived"] is True

        client.post("/api/v1/auth/logout", headers=headers)
        anonymous = client.get(f"/api/v1/catalog/coffee/{coffee['id']}/insights").json()
        assert anonymous["ratings_visible"] is False
        assert anonymous["rating_count"] is None
        assert anonymous["average_liking"] is None
        assert all(brew["rating_count"] is None for brew in anonymous["recent_brews"])
        assert client.get(f"/api/v1/grinders/{grinder['id']}").status_code == 401
        assert client.get(f"/api/v1/catalog/grinder/{grinder['id']}/insights").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        assert login.status_code == 200
        assert login.json()["profile"]["pin_change_required"] is True
        pin_required = client.get(f"/api/v1/catalog/grinder/{grinder['id']}/insights").json()
        assert pin_required["ratings_visible"] is False
        assert pin_required["rating_count"] is None


def test_coffee_and_brew_rating_insights(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Insight Roasters", "name": "Weighted Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        def completed_brew(setting: int) -> dict:
            created = client.post(
                "/api/v1/brews",
                headers=admin_headers,
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 92,
                    "grinder_setting": setting,
                },
            ).json()
            finalized = client.post(
                f"/api/v1/brews/{created['id']}/finalize",
                headers=admin_headers,
                json={"total_brew_time_s": 180 + setting},
            )
            assert finalized.status_code == 200, finalized.text
            return finalized.json()

        first_brew = completed_brew(20)
        second_brew = completed_brew(21)
        unrated_brew = completed_brew(22)
        voided_brew = completed_brew(23)
        draft_brew = client.post(
            "/api/v1/brews",
            headers=admin_headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 92,
                "grinder_setting": 24,
            },
        ).json()

        tags = client.get("/api/v1/flavor-tags?active_only=false").json()
        fruity = next(tag for tag in tags if tag["name"] == "Fruity" and tag["parent_id"] is None)
        fruity_child = next(tag for tag in tags if tag["parent_id"] == fruity["id"])

        def submit_rating(brew: dict, payload: dict, headers: dict[str, str]) -> None:
            response = client.post(
                f"/api/v1/brews/{brew['id']}/ratings", headers=headers, json=payload
            )
            assert response.status_code == 200, response.text

        submit_rating(
            first_brew,
            {
                "liking": 9,
                "acidity": 5,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [fruity["id"], fruity_child["id"]],
            },
            admin_headers,
        )
        submit_rating(
            second_brew,
            {
                "liking": 3,
                "acidity": 1,
                "bitterness": 5,
                "sweetness": 1,
                "body": 1,
                "flavor_tag_ids": [],
            },
            admin_headers,
        )
        submit_rating(
            voided_brew,
            {
                "liking": 1,
                "acidity": 1,
                "bitterness": 5,
                "sweetness": 0,
                "body": 1,
                "flavor_tag_ids": [fruity["id"]],
            },
            admin_headers,
        )
        assert (
            client.post(
                f"/api/v1/brews/{voided_brew['id']}/void", headers=admin_headers
            ).status_code
            == 200
        )

        client.post("/api/v1/auth/logout", headers=admin_headers)
        assert client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").status_code == 401
        assert client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert login.json()["profile"]["pin_change_required"] is True
        assert client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").status_code == 403
        assert client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights").status_code == 403
        assert (
            client.post(
                "/api/v1/auth/pin",
                headers=member_headers,
                json={"current_pin": "5678", "new_pin": "6789"},
            ).status_code
            == 204
        )

        visible_without_own_rating = client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights")
        assert visible_without_own_rating.status_code == 200
        assert visible_without_own_rating.json()["count"] == 1
        assert client.get(f"/api/v1/brews/{draft_brew['id']}/rating-insights").status_code == 409
        assert client.get("/api/v1/coffees/99999/rating-insights").status_code == 404

        submit_rating(
            first_brew,
            {
                "liking": 7,
                "acidity": 3,
                "bitterness": 3,
                "sweetness": 2,
                "body": 5,
                "flavor_tag_ids": [fruity_child["id"]],
            },
            member_headers,
        )

        first_page = client.get(
            f"/api/v1/coffees/{coffee['id']}/rating-insights?limit=1&offset=0"
        ).json()
        assert first_page["rated_brew_count"] == 2
        assert first_page["next_offset"] == 1
        assert [item["brew"]["id"] for item in first_page["rated_brews"]] == [second_brew["id"]]
        assert first_page["rated_brews"][0]["brew"]["rating_token"] is None
        assert "ratings" not in first_page["rated_brews"][0]
        assert "profile" not in first_page["rated_brews"][0]
        assert first_page["aggregate"]["count"] == 3
        assert first_page["aggregate"]["averages"] == {
            "liking": 6.33,
            "acidity": 3,
            "bitterness": 3,
            "sweetness": 2.33,
            "body": 3,
        }
        coffee_fruity = next(
            axis for axis in first_page["aggregate"]["flavor_axes"] if axis["label"] == "Fruity"
        )
        assert coffee_fruity == {
            "id": fruity["id"],
            "label": "Fruity",
            "mentions": 2,
            "total": 3,
        }

        second_page = client.get(
            f"/api/v1/coffees/{coffee['id']}/rating-insights?limit=1&offset=1"
        ).json()
        assert second_page["next_offset"] is None
        assert [item["brew"]["id"] for item in second_page["rated_brews"]] == [first_brew["id"]]
        assert second_page["aggregate"] == first_page["aggregate"]
        first_brew_aggregate = second_page["rated_brews"][0]["aggregate"]
        assert first_brew_aggregate["averages"] == {
            "liking": 8,
            "acidity": 4,
            "bitterness": 2,
            "sweetness": 3,
            "body": 4,
        }
        first_brew_fruity = next(
            axis for axis in first_brew_aggregate["flavor_axes"] if axis["label"] == "Fruity"
        )
        assert first_brew_fruity["mentions"] == 2
        assert first_brew_fruity["total"] == 2

        empty_aggregate = client.get(f"/api/v1/brews/{unrated_brew['id']}/rating-insights").json()
        assert empty_aggregate["count"] == 0
        assert empty_aggregate["averages"] == {}
        assert all(
            axis["mentions"] == 0 and axis["total"] == 0 for axis in empty_aggregate["flavor_axes"]
        )

        client.post("/api/v1/auth/logout", headers=member_headers)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}

        def update_tag(
            tag: dict, *, active: bool | None = None, sort_order: int | None = None
        ) -> None:
            response = client.put(
                f"/api/v1/flavor-tags/{tag['id']}",
                headers=admin_headers,
                json={
                    "name": tag["name"],
                    "parent_id": tag["parent_id"],
                    "active": tag["active"] if active is None else active,
                    "sort_order": tag["sort_order"] if sort_order is None else sort_order,
                },
            )
            assert response.status_code == 200, response.text

        reordered_parent = next(
            tag for tag in reversed(tags) if tag["parent_id"] is None and tag["id"] != fruity["id"]
        )
        update_tag(reordered_parent, sort_order=-1)
        reordered = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert reordered["aggregate"]["flavor_axes"][0]["id"] == reordered_parent["id"]
        update_tag(reordered_parent, sort_order=reordered_parent["sort_order"])

        update_tag(fruity_child, active=False)
        historical_child = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        historical_fruity = next(
            axis
            for axis in historical_child["aggregate"]["flavor_axes"]
            if axis["label"] == "Fruity"
        )
        assert historical_fruity["mentions"] == 2

        update_tag(fruity, active=False)
        inactive_axis = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert "Fruity" not in {axis["label"] for axis in inactive_axis["aggregate"]["flavor_axes"]}
        for parent in (
            tag for tag in tags if tag["parent_id"] is None and tag["id"] != fruity["id"]
        ):
            update_tag(parent, active=False)
        no_axes = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert no_axes["aggregate"]["flavor_axes"] == []


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

        fruity = next(
            item
            for item in client.get("/api/v1/flavor-tags").json()
            if item["name"] == "Fruity" and item["parent_id"] is None
        )
        admin_rating = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=headers,
            json={
                "liking": 7,
                "acidity": 4,
                "bitterness": 2,
                "sweetness": 3,
                "body": 4,
                "flavor_tag_ids": [fruity["id"]],
            },
        )
        assert admin_rating.status_code == 200
        admin_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert set(admin_profile["profile"]) == {"id", "display_name"}
        assert admin_profile["is_self"] is True
        assert admin_profile["is_complete_history"] is True
        assert admin_profile["rating_count"] == 1
        assert admin_profile["favorite_coffees"][0]["average_liking"] == 7
        admin_comparison = admin_profile["ratings"][0]
        assert admin_comparison["selected_flavors"] == ["Fruity"]
        assert admin_comparison["peer_count"] == 0
        assert admin_comparison["peer_averages"] == {}
        assert admin_comparison["peer_deltas"] == {}
        assert admin_profile["next_offset"] is None

        client.post("/api/v1/auth/logout", headers=headers)
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/profiles/1/ratings").status_code == 401
        assert client.get(f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}").status_code == 401
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
        hidden_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert set(hidden_profile["profile"]) == {"id", "display_name"}
        assert hidden_profile["is_self"] is False
        assert hidden_profile["is_complete_history"] is False
        assert hidden_profile["rating_count"] == 0
        assert hidden_profile["ratings"] == []
        assert hidden_profile["averages"] == {}
        assert client.get("/api/v1/profiles/99999/ratings").status_code == 404
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
            "flavor_axes": [],
        }
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
        assert rated.json()["averages"]["liking"] == 7.5
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
        assert updated.json()["count"] == 2
        assert updated.json()["averages"]["liking"] == 8

        own_profile = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert own_profile["is_self"] is True
        assert own_profile["is_complete_history"] is True
        assert own_profile["averages"] == {
            "liking": 9,
            "acidity": 2,
            "bitterness": 1,
            "sweetness": 5,
            "body": 3,
        }
        assert own_profile["favorite_coffees"] == [
            {
                "coffee_id": coffee["id"],
                "coffee_name": "Collider Blend",
                "coffee_roaster": "PSI Roasters",
                "rating_count": 1,
                "average_liking": 9,
            }
        ]
        comparison = own_profile["ratings"][0]
        assert comparison["total_rating_count"] == 2
        assert comparison["peer_count"] == 1
        assert comparison["peer_averages"] == {
            "liking": 7,
            "acidity": 4,
            "bitterness": 2,
            "sweetness": 3,
            "body": 4,
        }
        assert comparison["peer_deltas"] == {
            "liking": 2,
            "acidity": -2,
            "bitterness": -1,
            "sweetness": 2,
            "body": -1,
        }
        assert comparison["peer_flavor_counts"] == {"Fruity": 1}

        shared_admin_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert shared_admin_profile["rating_count"] == 1
        assert shared_admin_profile["ratings"][0]["rating"]["liking"] == 7
        assert shared_admin_profile["ratings"][0]["peer_deltas"]["liking"] == -2

        scoped_comparisons = client.get(
            f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}"
        ).json()
        assert [item["brew_id"] for item in scoped_comparisons] == [brew["id"]]
        assert scoped_comparisons[0]["peer_averages"]["liking"] == 7
        assert client.get("/api/v1/ratings/me/comparisons").status_code == 422
        duplicate_ids = client.get(
            f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}&brew_id={brew['id']}"
        )
        assert duplicate_ids.status_code == 422
        too_many_ids = "&".join(f"brew_id={item}" for item in range(1, 52))
        assert client.get(f"/api/v1/ratings/me/comparisons?{too_many_ids}").status_code == 422

        second_coffee = client.post(
            "/api/v1/coffees",
            headers=member_headers,
            json={"roaster": "Quiet Roasters", "name": "Solo Lot"},
        ).json()
        second_brew = client.post(
            "/api/v1/brews",
            headers=member_headers,
            json={
                "coffee_id": second_coffee["id"],
                "grinder_id": grinder["id"],
                "dripper_id": dripper["id"],
                "filter_id": brew_filter["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 92,
                "grinder_setting": 29,
            },
        ).json()
        client.post(
            f"/api/v1/brews/{second_brew['id']}/finalize",
            headers=member_headers,
            json={"total_brew_time_s": 190},
        )
        second_rating = client.post(
            f"/api/v1/brews/{second_brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 6,
                "acidity": 1,
                "bitterness": 4,
                "sweetness": 2,
                "body": 5,
                "flavor_tag_ids": [],
            },
        )
        assert second_rating.status_code == 200

        comparison_ids = (second_brew["id"], brew["id"])
        comparison_query = "&".join(f"brew_id={item}" for item in comparison_ids)
        comparisons = client.get(f"/api/v1/ratings/me/comparisons?{comparison_query}").json()
        assert [item["brew_id"] for item in comparisons] == list(comparison_ids)
        assert comparisons[0]["peer_count"] == 0
        assert comparisons[0]["peer_averages"] == {}
        assert comparisons[0]["peer_deltas"] == {}
        assert comparisons[1]["peer_count"] == 1

        first_page = client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=1&offset=0").json()
        assert first_page["rating_count"] == 2
        assert first_page["next_offset"] == 1
        assert [item["brew"]["id"] for item in first_page["ratings"]] == [second_brew["id"]]
        assert first_page["averages"] == {
            "liking": 7.5,
            "acidity": 1.5,
            "bitterness": 2.5,
            "sweetness": 3.5,
            "body": 4,
        }
        assert [item["coffee_name"] for item in first_page["favorite_coffees"]] == [
            "Collider Blend",
            "Solo Lot",
        ]
        second_page = client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=1&offset=1").json()
        assert second_page["rating_count"] == 2
        assert second_page["next_offset"] is None
        assert [item["brew"]["id"] for item in second_page["ratings"]] == [brew["id"]]
        assert second_page["averages"] == first_page["averages"]
        assert second_page["favorite_coffees"] == first_page["favorite_coffees"]
        assert client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=101").status_code == 422
        assert client.get(f"/api/v1/profiles/{member['id']}/ratings?offset=-1").status_code == 422

        client.post("/api/v1/auth/logout", headers=member_headers)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        complete_member_profile = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert complete_member_profile["rating_count"] == 2
        assert (
            client.post(
                f"/api/v1/brews/{second_brew['id']}/void", headers=admin_headers
            ).status_code
            == 200
        )
        profile_after_void = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert profile_after_void["rating_count"] == 1
        assert [item["brew"]["id"] for item in profile_after_void["ratings"]] == [brew["id"]]
        corrected = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=admin_headers,
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
            headers=admin_headers,
        )
        assert voided.status_code == 200
        repeat_void = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers=admin_headers,
        )
        assert repeat_void.status_code == 409
        assert repeat_void.json()["detail"] == "Only completed brews can be voided"
        inactive = client.get(f"/api/v1/rating-links/{finalized['rating_token']}").json()
        assert inactive == {"active": False, "brew": None}


def test_brew_operator_reassignment_and_operator_corrections(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        grace = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        linus = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Linus", "pin": "6789", "role": "member"},
        ).json()
        inactive_operator = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Inactive", "pin": "7890", "role": "member"},
        ).json()
        for profile in (grace, linus):
            response = client.put(
                f"/api/v1/people/{profile['id']}",
                headers=admin_headers,
                json={"pin_change_required": False},
            )
            assert response.status_code == 200
        response = client.put(
            f"/api/v1/people/{inactive_operator['id']}",
            headers=admin_headers,
            json={"active": False},
        )
        assert response.status_code == 200

        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Reassignment", "name": "Operator Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        brew_input = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }

        def login(profile_id: int, pin: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={"profile_id": profile_id, "pin": pin, "device_mode": "personal"},
            )
            assert response.status_code == 200, response.text
            return {"X-CSRF-Token": response.json()["csrf_token"]}

        grace_headers = login(grace["id"], "5678")
        admin_transfer = client.post("/api/v1/brews", headers=grace_headers, json=brew_input).json()
        admin_headers = login(1, "1234")
        admin_reassigned = client.put(
            f"/api/v1/brews/{admin_transfer['id']}/operator",
            headers=admin_headers,
            json={"operator_id": linus["id"]},
        )
        assert admin_reassigned.status_code == 200
        assert admin_reassigned.json()["operator_name"] == "Linus"

        grace_headers = login(grace["id"], "5678")
        brew = client.post("/api/v1/brews", headers=grace_headers, json=brew_input).json()
        missing = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": 99999},
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Operator not found"
        inactive = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": inactive_operator["id"]},
        )
        assert inactive.status_code == 422
        assert inactive.json()["detail"] == "Operator must be active"

        linus_headers = login(linus["id"], "6789")
        forbidden = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=linus_headers,
            json={"operator_id": linus["id"]},
        )
        assert forbidden.status_code == 403

        grace_headers = login(grace["id"], "5678")
        reassigned = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": linus["id"]},
        )
        assert reassigned.status_code == 200
        assert reassigned.json()["operator_id"] == linus["id"]
        assert reassigned.json()["operator_name"] == "Linus"
        assert (
            client.put(
                f"/api/v1/brews/{brew['id']}", headers=grace_headers, json=brew_input
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=grace_headers,
                json={"total_brew_time_s": 180},
            ).status_code
            == 403
        )
        assert (
            client.post(f"/api/v1/brews/{brew['id']}/cancel", headers=grace_headers).status_code
            == 403
        )

        linus_headers = login(linus["id"], "6789")
        finalized_response = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=linus_headers,
            json={"total_brew_time_s": 180},
        )
        assert finalized_response.status_code == 200
        finalized = finalized_response.json()
        assert finalized["operator_id"] == linus["id"]
        rating_token = finalized["rating_token"]
        assert (
            client.put(
                f"/api/v1/brews/{brew['id']}/operator",
                headers=linus_headers,
                json={"operator_id": grace["id"]},
            ).status_code
            == 409
        )
        rated = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=linus_headers,
            json={
                "liking": 8,
                "acidity": 3,
                "bitterness": 2,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [],
            },
        )
        assert rated.status_code == 200

        correction = {
            **brew_input,
            "operator_id": grace["id"],
            "temperature_c": 93,
            "total_brew_time_s": 181,
        }
        corrected = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=linus_headers,
            json=correction,
        )
        assert corrected.status_code == 200
        assert corrected.json()["operator_id"] == grace["id"]
        assert corrected.json()["temperature_c"] == 93
        assert corrected.json()["rating_token"] == rating_token
        assert client.get(f"/api/v1/brews/{brew['id']}/ratings").json()["count"] == 1

        assert (
            client.put(
                f"/api/v1/brews/{brew['id']}/correction",
                headers=linus_headers,
                json=correction,
            ).status_code
            == 403
        )
        grace_headers = login(grace["id"], "5678")
        invalid_correction = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=grace_headers,
            json={**correction, "operator_id": inactive_operator["id"]},
        )
        assert invalid_correction.status_code == 422
        assert (
            client.post(f"/api/v1/brews/{brew['id']}/void", headers=grace_headers).status_code
            == 403
        )
        analytics = client.get("/api/v1/analytics").json()
        assert analytics["operator_counts"] == [
            {"profile_id": grace["id"], "display_name": "Grace", "brew_count": 1}
        ]

        admin_headers = login(1, "1234")
        admin_correction = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=admin_headers,
            json={key: value for key, value in correction.items() if key != "operator_id"},
        )
        assert admin_correction.status_code == 200
        assert admin_correction.json()["operator_id"] == grace["id"]


def test_concurrent_operator_transfers_are_atomic(tmp_path: Path, monkeypatch) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        grace = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        linus = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Linus", "pin": "6789", "role": "member"},
        ).json()
        for profile in (grace, linus):
            response = client.put(
                f"/api/v1/people/{profile['id']}",
                headers=admin_headers,
                json={"pin_change_required": False},
            )
            assert response.status_code == 200

        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Concurrency", "name": "Atomic Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        brew_input = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": grace["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        grace_headers = {"X-CSRF-Token": login["csrf_token"]}
        draft = client.post("/api/v1/brews", headers=grace_headers, json=brew_input).json()
        completed = client.post("/api/v1/brews", headers=grace_headers, json=brew_input).json()
        finalized = client.post(
            f"/api/v1/brews/{completed['id']}/finalize",
            headers=grace_headers,
            json={"total_brew_time_s": 180},
        )
        assert finalized.status_code == 200

        barrier = Barrier(2)
        original_load_active_operator = api_module.load_active_operator

        def synchronized_load_active_operator(db, operator_id: int) -> Profile:
            operator = original_load_active_operator(db, operator_id)
            barrier.wait(timeout=5)
            return operator

        monkeypatch.setattr(api_module, "load_active_operator", synchronized_load_active_operator)

        def reassign_draft(operator_id: int) -> int:
            return client.put(
                f"/api/v1/brews/{draft['id']}/operator",
                headers=grace_headers,
                json={"operator_id": operator_id},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            draft_statuses = list(executor.map(reassign_draft, (1, linus["id"])))

        assert sorted(draft_statuses) == [200, 403]
        assert client.get(f"/api/v1/brews/{draft['id']}").json()["operator_id"] in {
            1,
            linus["id"],
        }

        def correct_completed_brew(target: tuple[int, int]) -> int:
            operator_id, temperature = target
            return client.put(
                f"/api/v1/brews/{completed['id']}/correction",
                headers=grace_headers,
                json={
                    **brew_input,
                    "operator_id": operator_id,
                    "temperature_c": temperature,
                    "total_brew_time_s": 181,
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            correction_statuses = list(
                executor.map(correct_completed_brew, ((1, 92), (linus["id"], 93)))
            )

        assert sorted(correction_statuses) == [200, 403]
        corrected = client.get(f"/api/v1/brews/{completed['id']}").json()
        assert (corrected["operator_id"], corrected["temperature_c"]) in {
            (1, 92),
            (linus["id"], 93),
        }


def test_export_omits_auth_secrets(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        response = client.get("/api/v1/exports/json")
        assert response.status_code == 200
        body = response.text
        assert "pin_hash" not in body
        assert "rating_token" not in body
        assert "failed_login_attempts" not in body
        assert "last_failed_login_at" not in body
        assert "login_blocked_until" not in body
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
