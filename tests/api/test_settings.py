from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from app import branding as branding_module
from app.routers import settings as settings_module
from sqlalchemy.orm import Session

from tests.api_helpers import bootstrap, build_client, image_upload, settings_payload


def test_public_settings_expose_the_deployed_version(tmp_path: Path) -> None:
    with build_client(tmp_path, app_version="v2026.08.5") as client:
        settings = client.get("/api/v1/settings").json()
        assert settings["app_version"] == "v2026.08.5"
        assert settings["brewing_logo_path"] == "/brand/filter-coffee-club-brewing.svg"


def test_brewing_logo_uploads_replace_clear_and_restore_cleanly(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)

        first_upload = client.post(
            "/api/v1/settings/brewing-logo",
            headers=headers,
            files={"logo": ("brewing.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert first_upload.status_code == 200, first_upload.text
        first_path = first_upload.json()["brewing_logo_path"]
        assert first_path.startswith("/uploads/brewing-logo-")
        assert first_path.endswith(".png")
        assert client.get(first_path).content.startswith(b"\x89PNG\r\n\x1a\n")

        replacement = client.post(
            "/api/v1/settings/brewing-logo",
            headers=headers,
            files={"logo": ("brewing.webp", image_upload("WEBP", size=(24, 24)), "image/webp")},
        )
        assert replacement.status_code == 200, replacement.text
        replacement_path = replacement.json()["brewing_logo_path"]
        assert replacement_path.startswith("/uploads/brewing-logo-")
        assert replacement_path.endswith(".webp")
        assert client.get(first_path).status_code == 404
        assert client.get(replacement_path).status_code == 200

        cleared = client.delete("/api/v1/settings/brewing-logo", headers=headers)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["brewing_logo_path"] is None
        assert client.get(replacement_path).status_code == 404

        restored = client.post("/api/v1/settings/brewing-logo/default", headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["brewing_logo_path"] == ("/brand/filter-coffee-club-brewing.svg")


def test_regular_logo_replacement_removes_previous_upload(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        first = client.post(
            "/api/v1/settings/logo",
            headers=headers,
            files={"logo": ("logo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert first.status_code == 200, first.text
        first_path = first.json()["logo_path"]

        replacement = client.post(
            "/api/v1/settings/logo",
            headers=headers,
            files={"logo": ("logo.webp", image_upload("WEBP", size=(24, 24)), "image/webp")},
        )
        assert replacement.status_code == 200, replacement.text
        assert client.get(first_path).status_code == 404
        assert client.get(replacement.json()["logo_path"]).status_code == 200


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_overlapping_logo_uploads_remove_the_superseded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resource: str
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        endpoint = f"/api/v1/settings/{resource}"
        initial = client.post(
            endpoint,
            headers=headers,
            files={"logo": ("initial.webp", image_upload("WEBP", size=(20, 20)), "image/webp")},
        )
        assert initial.status_code == 200
        slow_upload_stored = Event()
        allow_slow_upload = Event()
        store_logo = branding_module.store_logo

        async def pause_png_upload(content, content_type, settings, filename_prefix):
            path = await store_logo(content, content_type, settings, filename_prefix)
            if content_type == "image/png":
                slow_upload_stored.set()
                assert await asyncio.to_thread(allow_slow_upload.wait, 10)
            return path

        monkeypatch.setattr(branding_module, "store_logo", pause_png_upload)
        with ThreadPoolExecutor(max_workers=1) as executor:
            slow = executor.submit(
                client.post,
                endpoint,
                headers=headers,
                files={"logo": ("slow.png", image_upload(size=(20, 20)), "image/png")},
            )
            try:
                assert slow_upload_stored.wait(timeout=10)
                fast = client.post(
                    endpoint,
                    headers=headers,
                    files={
                        "logo": ("fast.webp", image_upload("WEBP", size=(24, 24)), "image/webp")
                    },
                )
                assert fast.status_code == 200, fast.text
            finally:
                allow_slow_upload.set()
            final = slow.result(timeout=10)

        assert final.status_code == 200, final.text
        attribute = "logo_path" if resource == "logo" else "brewing_logo_path"
        final_path = final.json()[attribute]
        assert client.get("/api/v1/settings").json()[attribute] == final_path
        assert client.get(final_path).status_code == 200
        assert client.get(fast.json()[attribute]).status_code == 404
        assert list((tmp_path / "uploads").glob(f"{resource}-*")) == [
            tmp_path / "uploads" / Path(final_path).name
        ]


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_status", "expected_detail"),
    [
        ("logo.txt", b"not an image", "text/plain", 415, "Logo must be PNG or WebP"),
        (
            "logo.png",
            b"\x89PNG\r\n\x1a\ntruncated",
            "image/png",
            415,
            "Logo contents do not match its file type",
        ),
        (
            "logo.png",
            b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024),
            "image/png",
            413,
            "Logo exceeds 2 MB",
        ),
        (
            "logo.webp",
            image_upload(size=(20, 20)),
            "image/webp",
            415,
            "Logo contents do not match its file type",
        ),
    ],
)
def test_logo_upload_validation(
    tmp_path: Path,
    resource: str,
    filename: str,
    content: bytes,
    content_type: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        response = client.post(
            f"/api/v1/settings/{resource}",
            headers=headers,
            files={"logo": (filename, content, content_type)},
        )
        assert response.status_code == expected_status, response.text
        assert response.json()["detail"] == expected_detail
        assert list(client.app.state.settings.upload_dir.iterdir()) == [
            client.app.state.settings.catalog_upload_dir
        ]


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_logo_rejects_excessive_dimensions(tmp_path: Path, resource: str) -> None:
    with build_client(tmp_path, max_logo_pixels=100) as client:
        _session, headers = bootstrap(client)
        response = client.post(
            f"/api/v1/settings/{resource}",
            headers=headers,
            files={"logo": ("large.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert response.status_code == 413, response.text
        assert response.json()["detail"] == "Logo dimensions are too large"


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_logo_upload_requires_csrf(tmp_path: Path, resource: str) -> None:
    with build_client(tmp_path) as client:
        bootstrap(client)
        response = client.post(
            f"/api/v1/settings/{resource}",
            files={"logo": ("brewing.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_logo_upload_requires_admin(tmp_path: Path, resource: str) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Member", "pin": "5678", "role": "member"},
        ).json()
        updated = client.put(
            f"/api/v1/people/{member['id']}",
            headers=admin_headers,
            json={"pin_change_required": False},
        )
        assert updated.status_code == 200
        session = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        response = client.post(
            f"/api/v1/settings/{resource}",
            headers={"X-CSRF-Token": session["csrf_token"]},
            files={"logo": ("logo.png", image_upload(size=(20, 20)), "image/png")},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Administrator access required"
        assert list((tmp_path / "uploads").glob(f"{resource}-*")) == []


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_failed_logo_commit_removes_new_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resource: str
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)

        def fail_commit(_session: Session) -> None:
            raise RuntimeError("forced branding commit failure")

        monkeypatch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="forced branding commit failure"):
            client.post(
                f"/api/v1/settings/{resource}",
                headers=headers,
                files={"logo": ("brewing.png", image_upload(size=(20, 20)), "image/png")},
            )
        assert list((tmp_path / "uploads").glob(f"{resource}-*")) == []


@pytest.mark.parametrize("resource", ["logo", "brewing-logo"])
def test_logo_settings_lookup_failure_writes_no_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resource: str
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)

        def fail_lookup(_db: Session) -> None:
            raise RuntimeError("Settings lookup failed")

        monkeypatch.setattr(settings_module, "get_settings", fail_lookup)
        with pytest.raises(RuntimeError, match="Settings lookup failed"):
            client.post(
                f"/api/v1/settings/{resource}",
                headers=headers,
                files={"logo": ("logo.png", image_upload(size=(20, 20)), "image/png")},
            )
        assert list((tmp_path / "uploads").glob(f"{resource}-*")) == []


def test_render_deployments_fall_back_to_the_short_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FCC_APP_VERSION", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef0123456789abcdef0123456789abcdef01")
    with build_client(tmp_path) as client:
        assert client.get("/api/v1/settings").json()["app_version"] == "abcdef0"


def test_settings_reject_low_contrast_palette(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        settings = client.get("/api/v1/settings").json()
        payload = settings_payload(settings, max_active_brews=settings["max_active_brews"])
        payload["color_cyan"] = "#B8B8B8"

        response = client.put("/api/v1/settings", headers=headers, json=payload)

        assert response.status_code == 422
        assert "at least 4.5:1 contrast" in response.text


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
