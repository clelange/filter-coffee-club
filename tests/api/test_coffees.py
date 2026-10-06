from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from app.models import (
    Coffee,
)
from app.routers import coffees as coffees_module
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.api_helpers import bootstrap, build_client


def test_coffee_purchase_location_lifecycle_and_exports(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)

        without_location = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Unknown source"},
        )
        assert without_location.status_code == 200
        assert without_location.json()["purchase_location"] is None

        blank_location = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={
                "roaster": "Orbit",
                "name": "Blank source",
                "purchase_location": "   ",
            },
        )
        assert blank_location.status_code == 200
        assert blank_location.json()["purchase_location"] is None

        payload = {
            "roaster": "MAME",
            "name": "Ethiopia Bombe",
            "country": "Ethiopia",
            "purchase_location": "  MAME, Zurich  ",
        }
        created = client.post("/api/v1/coffees", headers=headers, json=payload)
        assert created.status_code == 200, created.text
        coffee = created.json()
        assert coffee["purchase_location"] == "MAME, Zurich"
        assert client.get(f"/api/v1/coffees/{coffee['id']}").json()["purchase_location"] == (
            "MAME, Zurich"
        )
        assert any(
            item["id"] == coffee["id"] and item["purchase_location"] == "MAME, Zurich"
            for item in client.get("/api/v1/coffees").json()
        )

        updated = client.put(
            f"/api/v1/coffees/{coffee['id']}",
            headers=headers,
            json={**payload, "purchase_location": "Coffee Collective, Copenhagen"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["purchase_location"] == "Coffee Collective, Copenhagen"

        clone = client.post(f"/api/v1/coffees/{coffee['id']}/clone", headers=headers, json={})
        assert clone.status_code == 200, clone.text
        assert clone.json()["purchase_location"] == "Coffee Collective, Copenhagen"

        too_long = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Long trip", "purchase_location": "x" * 161},
        )
        assert too_long.status_code == 422

        exported = client.get("/api/v1/exports/json").json()
        exported_coffee = next(item for item in exported["coffees"] if item["id"] == coffee["id"])
        assert exported_coffee["purchase_location"] == "Coffee Collective, Copenhagen"

        csv_response = client.get("/api/v1/exports/csv")
        with zipfile.ZipFile(io.BytesIO(csv_response.content)) as archive:
            coffees_csv = archive.read("coffees.csv").decode()
        assert "purchase_location" in coffees_csv
        assert "Coffee Collective, Copenhagen" in coffees_csv


def test_member_can_finish_restore_and_export_coffee(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Orbit", "name": "Last bag"},
        ).json()
        assert coffee["finished_at"] is None
        assert coffee["available"] is True

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
        member_session = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        member_headers = {"X-CSRF-Token": member_session["csrf_token"]}
        finished = client.post(f"/api/v1/coffees/{coffee['id']}/finish", headers=member_headers)
        assert finished.status_code == 200
        finished_coffee = finished.json()
        assert finished_coffee["finished_at"] is not None
        assert finished_coffee["available"] is False
        denied_archive = client.post(
            f"/api/v1/coffees/{coffee['id']}/archive", headers=member_headers
        )
        assert denied_archive.status_code == 403
        assert denied_archive.json()["detail"] == "Administrator access required"
        repeated_finish = client.post(
            f"/api/v1/coffees/{coffee['id']}/finish", headers=member_headers
        ).json()
        assert repeated_finish["finished_at"] == finished_coffee["finished_at"]

        assert all(item["id"] != coffee["id"] for item in client.get("/api/v1/coffees").json())
        assert any(
            item["id"] == coffee["id"]
            for item in client.get("/api/v1/coffees?include_finished=true").json()
        )
        assert any(
            item["id"] == coffee["id"]
            for item in client.get("/api/v1/coffees?include_archived=true").json()
        )

        cloned_bag = client.post(
            f"/api/v1/coffees/{coffee['id']}/clone", headers=member_headers, json={}
        ).json()
        assert cloned_bag["finished_at"] is None
        assert cloned_bag["available"] is True

        restored = client.post(f"/api/v1/coffees/{coffee['id']}/restore", headers=member_headers)
        assert restored.status_code == 200
        assert restored.json()["finished_at"] is None
        assert restored.json()["available"] is True
        repeated_restore = client.post(
            f"/api/v1/coffees/{coffee['id']}/restore", headers=member_headers
        ).json()
        assert repeated_restore["finished_at"] is None

        client.post("/api/v1/auth/logout", headers=member_headers)
        assert client.post(f"/api/v1/coffees/{coffee['id']}/finish").status_code == 401
        admin_session = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_session["csrf_token"]}
        client.post(f"/api/v1/coffees/{coffee['id']}/finish", headers=admin_headers)

        exported = client.get("/api/v1/exports/json").json()
        exported_coffee = next(item for item in exported["coffees"] if item["id"] == coffee["id"])
        assert exported_coffee["finished_at"] is not None
        csv_response = client.get("/api/v1/exports/csv")
        with zipfile.ZipFile(io.BytesIO(csv_response.content)) as archive:
            coffees_csv = archive.read("coffees.csv").decode()
        assert "finished_at" in coffees_csv.splitlines()[0]

        archived = client.post(f"/api/v1/coffees/{coffee['id']}/archive", headers=admin_headers)
        assert archived.status_code == 200
        assert archived.json()["available"] is False
        assert (
            client.post(f"/api/v1/coffees/{coffee['id']}/finish", headers=admin_headers).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/coffees/{coffee['id']}/restore", headers=admin_headers
            ).status_code
            == 409
        )


def test_coffee_creation_is_idempotent(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        idempotent_headers = {**headers, "Idempotency-Key": "coffee-create-test-key"}
        payload = {"roaster": "Orbit", "name": "Single bag", "country": "Ethiopia"}

        first = client.post("/api/v1/coffees", headers=idempotent_headers, json=payload)
        replay = client.post("/api/v1/coffees", headers=idempotent_headers, json=payload)

        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["id"] == first.json()["id"]
        assert len(client.get("/api/v1/coffees").json()) == 1

        conflict = client.post(
            "/api/v1/coffees",
            headers=idempotent_headers,
            json={**payload, "name": "Different bag"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"].startswith("Idempotency key was already used")
        assert len(client.get("/api/v1/coffees").json()) == 1

        edited_payload = {**payload, "name": "Edited bag"}
        edited = client.put(
            f"/api/v1/coffees/{first.json()['id']}", headers=headers, json=edited_payload
        )
        replay_after_edit = client.post("/api/v1/coffees", headers=idempotent_headers, json=payload)
        changed_request_after_edit = client.post(
            "/api/v1/coffees", headers=idempotent_headers, json=edited_payload
        )

        assert edited.status_code == 200
        assert replay_after_edit.status_code == 200
        assert replay_after_edit.json()["id"] == first.json()["id"]
        assert replay_after_edit.json()["name"] == "Edited bag"
        assert changed_request_after_edit.status_code == 409


def test_coffee_creation_key_cannot_be_reused_by_another_profile(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        idempotency_key = "profile-scoped-coffee-create"
        payload = {"roaster": "Orbit", "name": "Single bag"}
        created = client.post(
            "/api/v1/coffees",
            headers={**admin_headers, "Idempotency-Key": idempotency_key},
            json=payload,
        )
        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        assert (
            client.put(
                f"/api/v1/people/{member['id']}",
                headers=admin_headers,
                json={"pin_change_required": False},
            ).status_code
            == 200
        )
        member_session = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        ).json()

        conflict = client.post(
            "/api/v1/coffees",
            headers={
                "X-CSRF-Token": member_session["csrf_token"],
                "Idempotency-Key": idempotency_key,
            },
            json=payload,
        )

        assert created.status_code == 200
        assert conflict.status_code == 409
        assert len(client.get("/api/v1/coffees").json()) == 1


def test_concurrent_coffee_creation_with_same_key_commits_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        idempotent_headers = {**headers, "Idempotency-Key": "concurrent-coffee-create"}
        payload = {"roaster": "Orbit", "name": "Concurrent bag"}
        barrier = Barrier(2)
        original_enforce_demo_capacity = coffees_module.enforce_demo_capacity

        def synchronized_enforce_demo_capacity(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            barrier.wait(timeout=5)
            original_enforce_demo_capacity(*args, **kwargs)

        monkeypatch.setattr(
            coffees_module, "enforce_demo_capacity", synchronized_enforce_demo_capacity
        )

        def create_coffee(_attempt: int) -> tuple[int, int]:
            response = client.post("/api/v1/coffees", headers=idempotent_headers, json=payload)
            return response.status_code, response.json()["id"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create_coffee, range(2)))

        assert [status for status, _coffee_id in results] == [200, 200]
        assert len({coffee_id for _status, coffee_id in results}) == 1
        assert len(client.get("/api/v1/coffees").json()) == 1


def test_unrelated_integrity_error_is_not_an_idempotency_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        original_commit = Session.commit

        def fail_coffee_commit(db: Session) -> None:
            if any(isinstance(item, Coffee) for item in db.new):
                raise IntegrityError("forced statement", {}, RuntimeError("forced failure"))
            original_commit(db)

        monkeypatch.setattr(Session, "commit", fail_coffee_commit)

        with pytest.raises(IntegrityError, match="forced failure"):
            client.post(
                "/api/v1/coffees",
                headers={**headers, "Idempotency-Key": "unrelated-integrity-error"},
                json={"roaster": "Orbit", "name": "Failed bag"},
            )

        assert client.get("/api/v1/coffees").json() == []


def test_coffee_chart_colors_are_assigned_validated_and_exported(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        first = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Alpha"},
        ).json()
        assert first["chart_color"] == "#0072B2"

        preserved = client.put(
            f"/api/v1/coffees/{first['id']}",
            headers=headers,
            json={"roaster": "Orbit", "name": "Alpha edited"},
        ).json()
        assert preserved["chart_color"] == "#0072B2"

        customized = client.put(
            f"/api/v1/coffees/{first['id']}",
            headers=headers,
            json={
                "roaster": "Orbit",
                "name": "Alpha edited",
                "chart_color": "#abcdef",
            },
        ).json()
        assert customized["chart_color"] == "#ABCDEF"

        second = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Beta"},
        ).json()
        assert second["chart_color"] == "#0072B2"

        reassigned = client.put(
            f"/api/v1/coffees/{first['id']}",
            headers=headers,
            json={"roaster": "Orbit", "name": "Alpha edited", "chart_color": None},
        ).json()
        assert reassigned["chart_color"] == "#D55E00"

        clone = client.post(f"/api/v1/coffees/{first['id']}/clone", headers=headers, json={}).json()
        assert clone["chart_color"] == "#009E73"
        assert clone["chart_color"] != reassigned["chart_color"]

        for index in range(5):
            client.post(
                "/api/v1/coffees",
                headers=headers,
                json={"roaster": "Orbit", "name": f"Palette {index}"},
            )
        clone_after_full_palette = client.post(
            f"/api/v1/coffees/{second['id']}/clone", headers=headers, json={}
        ).json()
        assert clone_after_full_palette["chart_color"] != second["chart_color"]

        invalid = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Invalid", "chart_color": "blue"},
        )
        assert invalid.status_code == 422
        assert "Chart color must use #RRGGBB format" in invalid.text

        exported = client.get("/api/v1/exports/json").json()
        colors_by_id = {coffee["id"]: coffee["chart_color"] for coffee in exported["coffees"]}
        assert colors_by_id[first["id"]] == "#D55E00"
        assert colors_by_id[second["id"]] == "#0072B2"

        csv_response = client.get("/api/v1/exports/csv")
        with zipfile.ZipFile(io.BytesIO(csv_response.content)) as archive:
            coffees_csv = archive.read("coffees.csv").decode()
        assert "chart_color" in coffees_csv.splitlines()[0]
        assert "#D55E00" in coffees_csv


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("PUT", ""),
        ("POST", "/archive"),
        ("POST", "/finish"),
        ("POST", "/restore"),
        ("POST", "/clone"),
    ],
)
def test_coffee_commands_preserve_missing_resource_errors(
    tmp_path: Path, method: str, suffix: str
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        response = client.request(
            method,
            f"/api/v1/coffees/999{suffix}",
            headers=headers,
            json={"roaster": "Orbit", "name": "Missing bag"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Coffee not found"
