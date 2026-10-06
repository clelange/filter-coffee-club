from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from app import catalog_photos as catalog_photos_module
from PIL import Image

from tests.api_helpers import (
    animated_gif_upload,
    bootstrap,
    build_client,
    image_upload,
    multipicture_jpeg_upload,
)


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
            assert response.json()["photo_framing"] is None

            framed = client.patch(
                f"/api/v1/{resource}/{item['id']}/photo",
                headers=headers,
                json={"photo_framing": {"focus_x": 0.2, "focus_y": 0.75, "zoom": 1.6}},
            )
            assert framed.status_code == 200, framed.text
            assert framed.json()["photo_path"] == path
            assert framed.json()["photo_framing"] == {
                "focus_x": 0.2,
                "focus_y": 0.75,
                "zoom": 1.6,
            }

            reset = client.patch(
                f"/api/v1/{resource}/{item['id']}/photo",
                headers=headers,
                json={"photo_framing": None},
            )
            assert reset.status_code == 200, reset.text
            assert reset.json()["photo_framing"] is None

        coffee_path = client.get(f"/api/v1/coffees/{coffee['id']}").json()["photo_path"]
        replacement = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            data={"focus_x": "0.8", "focus_y": "0.25", "zoom": "2.25"},
            files={"photo": ("replacement.jpg", image_upload("JPEG", (400, 600)), "image/jpeg")},
        )
        assert replacement.status_code == 200
        replacement_path = replacement.json()["photo_path"]
        assert replacement.json()["photo_framing"] == {
            "focus_x": 0.8,
            "focus_y": 0.25,
            "zoom": 2.25,
        }
        assert replacement_path != coffee_path
        assert client.get(coffee_path).status_code == 404

        heic_upload = client.put(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            files={"photo": ("iphone.heic", image_upload("HEIF", (3024, 4032)), "image/heic")},
        )
        assert heic_upload.status_code == 200, heic_upload.text
        heic_path = heic_upload.json()["photo_path"]
        assert heic_upload.json()["photo_framing"] is None
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
        assert removed.json()["photo_framing"] is None
        assert client.get(replacement_path).status_code == 404

        no_photo_framing = client.patch(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers=headers,
            json={"photo_framing": {"focus_x": 0.5, "focus_y": 0.5, "zoom": 1}},
        )
        assert no_photo_framing.status_code == 409
        assert no_photo_framing.json()["detail"] == "Catalog item has no photo to frame"

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
        kiosk_framing = client.patch(
            f"/api/v1/coffees/{coffee['id']}/photo",
            headers={"X-CSRF-Token": kiosk_login["csrf_token"]},
            json={"photo_framing": None},
        )
        assert kiosk_framing.status_code == 403
        assert kiosk_framing.json()["detail"] == "Photo changes are unavailable in kiosk mode"


@pytest.mark.parametrize(
    ("resource", "payload"),
    [
        ("coffees", {"roaster": "Test", "name": "Photo validation"}),
        ("grinders", {"definition_key": "kingrinder_k6"}),
        ("drippers", {"manufacturer": "Test", "model": "Cone"}),
        ("filters", {"name": "Test paper"}),
    ],
)
def test_catalog_photo_validation_limits(tmp_path: Path, resource: str, payload: dict) -> None:
    size_path = tmp_path / "size-limit"
    with build_client(size_path, max_catalog_photo_bytes=32) as client:
        _session, headers = bootstrap(client)
        item = client.post(f"/api/v1/{resource}", headers=headers, json=payload).json()
        photo_url = f"/api/v1/{resource}/{item['id']}/photo"
        oversized = client.put(
            photo_url,
            headers=headers,
            files={"photo": ("photo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"] == "Photo exceeds 32 bytes"

    pixel_path = tmp_path / "pixel-limit"
    with build_client(pixel_path, max_catalog_photo_pixels=100) as client:
        _session, headers = bootstrap(client)
        item = client.post(f"/api/v1/{resource}", headers=headers, json=payload).json()
        photo_url = f"/api/v1/{resource}/{item['id']}/photo"
        missing_photo = client.patch(
            photo_url,
            headers=headers,
            json={"photo_framing": {"focus_x": 0.5, "focus_y": 0.5, "zoom": 1}},
        )
        assert missing_photo.status_code == 409
        assert missing_photo.json()["detail"] == "Catalog item has no photo to frame"

        excessive_resolution = client.put(
            photo_url,
            headers=headers,
            files={"photo": ("photo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert excessive_resolution.status_code == 413
        assert excessive_resolution.json()["detail"] == "Photo resolution is too large"

        unsupported = client.put(
            photo_url,
            headers=headers,
            files={"photo": ("photo.jpg", animated_gif_upload(), "image/jpeg")},
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["detail"] == "Animated photos are not supported"

        malformed = client.put(
            photo_url,
            headers=headers,
            files={"photo": ("photo.png", b"not an image", "image/png")},
        )
        assert malformed.status_code == 415
        assert malformed.json()["detail"] == "Photo is not a valid supported image"
        assert list(client.app.state.settings.catalog_upload_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("resource", "payload"),
    [
        ("coffees", {"roaster": "Test", "name": "Overlapping photos"}),
        ("grinders", {"definition_key": "kingrinder_k6"}),
        ("drippers", {"manufacturer": "Test", "model": "Cone"}),
        ("filters", {"name": "Test paper"}),
    ],
)
def test_overlapping_catalog_photos_remove_the_superseded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resource: str, payload: dict
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        item = client.post(f"/api/v1/{resource}", headers=headers, json=payload).json()
        endpoint = f"/api/v1/{resource}/{item['id']}/photo"
        initial = client.put(
            endpoint,
            headers=headers,
            files={"photo": ("initial.png", image_upload(size=(16, 16)), "image/png")},
        )
        assert initial.status_code == 200
        slow_write_started = Event()
        allow_slow_write = Event()
        atomic_write = catalog_photos_module._atomic_write

        def pause_small_photo_write(path: Path, content: bytes) -> None:
            with Image.open(io.BytesIO(content)) as image:
                is_slow = image.width == 20
            if is_slow:
                slow_write_started.set()
                assert allow_slow_write.wait(timeout=10)
            atomic_write(path, content)

        monkeypatch.setattr(catalog_photos_module, "_atomic_write", pause_small_photo_write)
        with ThreadPoolExecutor(max_workers=1) as executor:
            slow = executor.submit(
                client.put,
                endpoint,
                headers=headers,
                files={"photo": ("slow.png", image_upload(size=(20, 20)), "image/png")},
            )
            try:
                assert slow_write_started.wait(timeout=10)
                fast = client.put(
                    endpoint,
                    headers=headers,
                    files={"photo": ("fast.png", image_upload(size=(24, 24)), "image/png")},
                )
                assert fast.status_code == 200, fast.text
            finally:
                allow_slow_write.set()
            final = slow.result(timeout=10)

        assert final.status_code == 200, final.text
        final_path = final.json()["photo_path"]
        assert client.get(f"/api/v1/{resource}/{item['id']}").json()["photo_path"] == final_path
        assert client.get(final_path).status_code == 200
        assert client.get(fast.json()["photo_path"]).status_code == 404
        assert list(client.app.state.settings.catalog_upload_dir.iterdir()) == [
            client.app.state.settings.catalog_upload_dir / Path(final_path).name
        ]


def test_catalog_photo_framing_validation(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        uploaded = client.put(
            "/api/v1/grinders/1/photo",
            headers=headers,
            files={"photo": ("photo.png", image_upload(), "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
        original_path = uploaded.json()["photo_path"]

        partial_upload = client.put(
            "/api/v1/grinders/1/photo",
            headers=headers,
            data={"focus_x": "0.5"},
            files={"photo": ("photo.png", image_upload(), "image/png")},
        )
        assert partial_upload.status_code == 422
        assert partial_upload.json()["detail"] == "Photo framing fields must be provided together"
        assert client.get("/api/v1/grinders/1").json()["photo_path"] == original_path

        for framing in (
            {"focus_x": -0.1, "focus_y": 0.5, "zoom": 1},
            {"focus_x": 0.5, "focus_y": 1.1, "zoom": 1},
            {"focus_x": 0.5, "focus_y": 0.5, "zoom": 0.9},
            {"focus_x": 0.5, "focus_y": 0.5, "zoom": 3.1},
        ):
            invalid = client.patch(
                "/api/v1/grinders/1/photo",
                headers=headers,
                json={"photo_framing": framing},
            )
            assert invalid.status_code == 422

        unchanged = client.get("/api/v1/grinders/1").json()
        assert unchanged["photo_path"] == original_path
        assert unchanged["photo_framing"] is None
