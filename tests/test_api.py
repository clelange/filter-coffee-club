from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest
from alembic import command
from alembic.config import Config
from app import api as api_module
from app.config import Settings
from app.demo import DEMO_PROFILE_NAMES, _write_attempts
from app.main import create_app
from app.models import AppSettings, Brew, Coffee, Profile
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


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


def test_coffee_chart_color_migration_backfills_existing_rows(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.sqlite3'}"
    project_root = Path(__file__).resolve().parents[1]
    config = Config(project_root / "alembic.ini")
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["skip_logging_config"] = True
    config.attributes["settings"] = Settings(data_dir=tmp_path, database_url=database_url)
    command.upgrade(config, "5b0f2ea51d47")

    engine = create_engine(database_url)
    now = "2026-08-08 00:00:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profiles
                    (id, display_name, pin_hash, role, active, created_at, updated_at)
                VALUES
                    (1, 'Ada', 'hash', 'admin', 1, :now, :now)
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO coffees
                    (id, roaster, name, archived, created_by_id, created_at, updated_at)
                VALUES
                    (:id, 'Orbit', :name, 0, 1, :now, :now)
                """
            ),
            [{"id": index, "name": f"Lot {index}", "now": now} for index in range(1, 11)],
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        colors = list(
            connection.execute(text("SELECT chart_color FROM coffees ORDER BY id")).scalars()
        )
        nullable = next(
            column["nullable"]
            for column in inspect(connection).get_columns("coffees")
            if column["name"] == "chart_color"
        )
    engine.dispose()
    assert colors == [
        "#0072B2",
        "#D55E00",
        "#009E73",
        "#CC79A7",
        "#A6761D",
        "#6A3D9A",
        "#B2182B",
        "#4D4D4D",
        "#0072B2",
        "#D55E00",
    ]
    assert nullable is False

    command.downgrade(config, "5b0f2ea51d47")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        column_names = {column["name"] for column in inspect(connection).get_columns("coffees")}
    engine.dispose()
    assert "chart_color" not in column_names


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
        original_enforce_demo_capacity = api_module.enforce_demo_capacity

        def synchronized_enforce_demo_capacity(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            barrier.wait(timeout=5)
            original_enforce_demo_capacity(*args, **kwargs)

        monkeypatch.setattr(api_module, "enforce_demo_capacity", synchronized_enforce_demo_capacity)

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


def settings_payload(settings: dict, max_active_brews: int) -> dict:
    return {
        "app_name": settings["app_name"],
        "subtitle": settings["subtitle"],
        "public_base_url": settings["public_base_url"],
        "color_cream": settings["color_cream"],
        "color_surface": settings["color_surface"],
        "color_ink": settings["color_ink"],
        "color_coffee": settings["color_coffee"],
        "color_cyan": settings["color_cyan"],
        "color_amber": settings["color_amber"],
        "max_active_brews": max_active_brews,
    }


def test_parallel_brew_capacity_is_atomic_and_admin_configurable(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Parallel", "name": "Capacity Lot"},
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

        def start_brew(_attempt: int) -> tuple[int, dict]:
            response = client.post("/api/v1/brews", headers=headers, json=brew_input)
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(start_brew, range(3)))

        assert sorted(status for status, _body in results) == [200, 200, 409]
        active = client.get("/api/v1/brews/active").json()
        assert active["active_count"] == 2
        assert active["max_active_brews"] == 2
        assert active["can_start"] is False

        settings = client.get("/api/v1/settings").json()
        raised = client.put(
            "/api/v1/settings",
            headers=headers,
            json=settings_payload(settings, max_active_brews=3),
        )
        assert raised.status_code == 200
        third = client.post("/api/v1/brews", headers=headers, json=brew_input).json()
        assert third["status"] == "draft"

        lowered = client.put(
            "/api/v1/settings",
            headers=headers,
            json=settings_payload(raised.json(), max_active_brews=1),
        )
        assert lowered.status_code == 200
        assert client.post("/api/v1/brews", headers=headers, json=brew_input).status_code == 409

        drafts = client.get("/api/v1/brews/active").json()["brews"]
        for index, brew in enumerate(drafts):
            cancelled = client.post(
                f"/api/v1/brews/{brew['id']}/cancel",
                headers=headers,
                json={"revision": brew["revision"]},
            )
            assert cancelled.status_code == 200
            state = client.get("/api/v1/brews/active").json()
            assert state["can_start"] is (index == len(drafts) - 1)

        replacement = client.post("/api/v1/brews", headers=headers, json=brew_input)
        assert replacement.status_code == 200
        with client.app.state.session_factory() as db:
            assert db.get(AppSettings, 1).active_brew_count == 1


def test_startup_reconciles_the_active_brew_counter(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Recovery", "name": "Counter drift"},
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
        assert client.post("/api/v1/brews", headers=headers, json=brew_input).status_code == 200
        with client.app.state.session_factory() as db:
            settings = db.get(AppSettings, 1)
            assert settings is not None
            settings.active_brew_count = 0
            db.commit()

    with build_client(tmp_path) as restarted_client:
        login = restarted_client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        headers = {"X-CSRF-Token": login["csrf_token"]}
        assert (
            restarted_client.post("/api/v1/brews", headers=headers, json=brew_input).status_code
            == 200
        )
        assert (
            restarted_client.post("/api/v1/brews", headers=headers, json=brew_input).status_code
            == 409
        )


def test_collaborators_join_edit_finalize_and_receive_analytics_credit(tmp_path: Path) -> None:
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
            client.put(
                f"/api/v1/people/{profile['id']}",
                headers=admin_headers,
                json={"pin_change_required": False},
            )
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Together", "name": "Shared Lot"},
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
        brew = client.post("/api/v1/brews", headers=admin_headers, json=brew_input).json()

        def login(profile: dict, pin: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={"profile_id": profile["id"], "pin": pin, "device_mode": "personal"},
            ).json()
            return {"X-CSRF-Token": response["csrf_token"]}

        grace_headers = login(grace, "5678")
        joined = client.post(
            f"/api/v1/brews/{brew['id']}/join", headers=grace_headers, json={}
        ).json()
        assert [operator["display_name"] for operator in joined["operators"]] == ["Ada", "Grace"]
        replay = client.post(
            f"/api/v1/brews/{brew['id']}/join", headers=grace_headers, json={}
        ).json()
        assert replay["revision"] == joined["revision"]

        linus_headers = login(linus, "6789")
        forbidden = client.put(
            f"/api/v1/brews/{brew['id']}",
            headers=linus_headers,
            json={**brew_input, "revision": joined["revision"]},
        )
        assert forbidden.status_code == 403
        linus_joined = client.post(
            f"/api/v1/brews/{brew['id']}/join", headers=linus_headers, json={}
        ).json()
        edited = client.put(
            f"/api/v1/brews/{brew['id']}",
            headers=linus_headers,
            json={**brew_input, "temperature_c": 92, "revision": linus_joined["revision"]},
        )
        assert edited.status_code == 200
        grace_headers = login(grace, "5678")
        stale = client.put(
            f"/api/v1/brews/{brew['id']}",
            headers=grace_headers,
            json={**brew_input, "revision": linus_joined["revision"]},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == "Brew changed; refresh and try again"

        collaborator_cancel = client.post(
            f"/api/v1/brews/{brew['id']}/cancel",
            headers=grace_headers,
            json={"revision": edited.json()["revision"]},
        )
        assert collaborator_cancel.status_code == 403
        finalized = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=grace_headers,
            json={"total_brew_time_s": 180, "revision": edited.json()["revision"]},
        )
        assert finalized.status_code == 200
        assert {operator["display_name"] for operator in finalized.json()["operators"]} == {
            "Ada",
            "Grace",
            "Linus",
        }
        analytics = client.get("/api/v1/analytics").json()
        assert analytics["operator_counts"] == [
            {"profile_id": 1, "display_name": "Ada", "brew_count": 1},
            {"profile_id": grace["id"], "display_name": "Grace", "brew_count": 1},
            {"profile_id": linus["id"], "display_name": "Linus", "brew_count": 1},
        ]


def test_concurrent_duplicate_joins_are_idempotent(tmp_path: Path, monkeypatch) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        bob = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Bob", "pin": "5678", "role": "member"},
        ).json()
        client.put(
            f"/api/v1/people/{bob['id']}",
            headers=admin_headers,
            json={"pin_change_required": False},
        )
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Race", "name": "Duplicate join"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        brew = client.post(
            "/api/v1/brews",
            headers=admin_headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30,
            },
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": bob["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        bob_headers = {"X-CSRF-Token": login["csrf_token"]}

        barrier = Barrier(2)
        original_is_brew_operator = api_module.is_brew_operator

        def synchronized_membership_check(loaded_brew: Brew, profile_id: int) -> bool:
            result = original_is_brew_operator(loaded_brew, profile_id)
            if profile_id == bob["id"] and not result:
                barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(api_module, "is_brew_operator", synchronized_membership_check)

        def join(_attempt: int):
            return client.post(f"/api/v1/brews/{brew['id']}/join", headers=bob_headers, json={})

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(join, range(2)))

        assert [response.status_code for response in responses] == [200, 200]
        assert {response.json()["revision"] for response in responses} == {brew["revision"] + 1}
        current = client.get(f"/api/v1/brews/{brew['id']}").json()
        assert [operator["display_name"] for operator in current["operators"]] == ["Ada", "Bob"]


def test_join_cannot_race_with_finalization(tmp_path: Path, monkeypatch) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        bob = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Bob", "pin": "5678", "role": "member"},
        ).json()
        client.put(
            f"/api/v1/people/{bob['id']}",
            headers=admin_headers,
            json={"pin_change_required": False},
        )
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Race", "name": "Finalize while joining"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        brew = client.post(
            "/api/v1/brews",
            headers=admin_headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30,
            },
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": bob["id"], "pin": "5678", "device_mode": "personal"},
        ).json()
        bob_headers = {"X-CSRF-Token": login["csrf_token"]}

        join_checked = Event()
        allow_join = Event()
        original_is_brew_operator = api_module.is_brew_operator

        def pause_join_after_membership_check(loaded_brew: Brew, profile_id: int) -> bool:
            result = original_is_brew_operator(loaded_brew, profile_id)
            if profile_id == bob["id"] and not result and not join_checked.is_set():
                join_checked.set()
                assert allow_join.wait(timeout=5)
            return result

        monkeypatch.setattr(api_module, "is_brew_operator", pause_join_after_membership_check)

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending_join = executor.submit(
                client.post,
                f"/api/v1/brews/{brew['id']}/join",
                headers=bob_headers,
                json={},
            )
            assert join_checked.wait(timeout=5)
            with build_client(tmp_path) as admin_client:
                admin_login = admin_client.post(
                    "/api/v1/auth/login",
                    json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
                ).json()
                finalized = admin_client.post(
                    f"/api/v1/brews/{brew['id']}/finalize",
                    headers={"X-CSRF-Token": admin_login["csrf_token"]},
                    json={"total_brew_time_s": 180, "revision": brew["revision"]},
                )
                assert finalized.status_code == 200
            allow_join.set()
            joined = pending_join.result(timeout=5)

        assert joined.status_code == 409
        current = client.get(f"/api/v1/brews/{brew['id']}").json()
        assert current["status"] == "completed"
        assert [operator["display_name"] for operator in current["operators"]] == ["Ada"]


def test_concurrent_finalization_releases_capacity_once(tmp_path: Path, monkeypatch) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Race", "name": "Finalize once"},
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
        brew = client.post("/api/v1/brews", headers=headers, json=brew_input).json()

        barrier = Barrier(2)
        original_commit_guarded = api_module.commit_guarded_brew_update

        def synchronized_commit(*args, **kwargs):
            barrier.wait(timeout=5)
            return original_commit_guarded(*args, **kwargs)

        monkeypatch.setattr(api_module, "commit_guarded_brew_update", synchronized_commit)

        def finalize(_attempt: int):
            return client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": 180, "revision": brew["revision"]},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(finalize, range(2)))

        assert sorted(response.status_code for response in responses) == [200, 409]
        assert client.get("/api/v1/brews/active").json()["active_count"] == 0
        assert client.post("/api/v1/brews", headers=headers, json=brew_input).status_code == 200
        assert client.post("/api/v1/brews", headers=headers, json=brew_input).status_code == 200
        assert client.post("/api/v1/brews", headers=headers, json=brew_input).status_code == 409


def test_correcting_a_solo_operator_replaces_analytics_attribution(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        bob = client.post(
            "/api/v1/people",
            headers=headers,
            json={"display_name": "Bob", "pin": "5678", "role": "member"},
        ).json()
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Correction", "name": "Solo operator"},
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
        brew = client.post("/api/v1/brews", headers=headers, json=brew_input).json()
        completed = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=headers,
            json={"total_brew_time_s": 180, "revision": brew["revision"]},
        ).json()

        corrected = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=headers,
            json={**brew_input, "operator_id": bob["id"], "total_brew_time_s": 180},
        )

        assert corrected.status_code == 200
        assert corrected.json()["operator_id"] == bob["id"]
        assert corrected.json()["revision"] == completed["revision"] + 1
        assert [operator["display_name"] for operator in corrected.json()["operators"]] == ["Bob"]
        assert client.get("/api/v1/analytics").json()["operator_counts"] == [
            {"profile_id": bob["id"], "display_name": "Bob", "brew_count": 1}
        ]


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
                json={"total_brew_time_s": 180, "revision": brew["revision"]},
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
                f"/api/v1/brews/{voided_brew['id']}/void",
                headers=admin_headers,
                json={"revision": voided_brew["revision"]},
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
                json={"total_brew_time_s": total_time, "revision": brew["revision"]},
            )
            assert finalized.status_code == 200, finalized.text
            completed.append(finalized.json())
            temperatures.append(temperature)
            throughputs.append(240 / total_time)

        draft = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        cancelled = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        assert (
            client.post(
                f"/api/v1/brews/{cancelled['id']}/cancel",
                headers=headers,
                json={"revision": cancelled["revision"]},
            ).status_code
            == 200
        )
        voided = client.post(f"/api/v1/brews/{completed[0]['id']}/clone", headers=headers).json()
        assert (
            client.post(
                f"/api/v1/brews/{voided['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": 200, "revision": voided["revision"]},
            ).status_code
            == 200
        )
        voided = client.get(f"/api/v1/brews/{voided['id']}").json()
        assert (
            client.post(
                f"/api/v1/brews/{voided['id']}/void",
                headers=headers,
                json={"revision": voided["revision"]},
            ).status_code
            == 200
        )
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
                json={"total_brew_time_s": 180 + setting, "revision": created["revision"]},
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
                f"/api/v1/brews/{voided_brew['id']}/void",
                headers=admin_headers,
                json={"revision": voided_brew["revision"]},
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

        with client.app.state.session_factory() as db:
            legacy_brew = db.get(Brew, second_brew["id"])
            assert legacy_brew is not None
            legacy_brew.total_brew_time_s = None
            db.commit()

        analytics_response = client.get("/api/v1/analytics")
        assert analytics_response.status_code == 200, analytics_response.text
        analytics = analytics_response.json()
        assert analytics["counts"] == {"brews": 3, "ratings": 3, "coffees": 1}
        assert {point["brew_id"] for point in analytics["scatter"]} == {
            first_brew["id"],
            second_brew["id"],
        }
        first_point = next(
            point for point in analytics["scatter"] if point["brew_id"] == first_brew["id"]
        )
        assert first_point["coffee_color"] == coffee["chart_color"]
        assert first_point["liking"] == 8
        assert first_point["ratings"] == 2
        assert first_point["rating_metrics"] == {
            "liking": {"average": 8, "minimum": 7, "maximum": 9},
            "acidity": {"average": 4, "minimum": 3, "maximum": 5},
            "bitterness": {"average": 2, "minimum": 1, "maximum": 3},
            "sweetness": {"average": 3, "minimum": 2, "maximum": 4},
            "body": {"average": 4, "minimum": 3, "maximum": 5},
        }
        assert first_point["grinder_unit"] == "clicks"
        assert first_point["target_flow_g_s"] is None
        assert first_point["overall_throughput_g_s"] == 1.2
        second_point = next(
            point for point in analytics["scatter"] if point["brew_id"] == second_brew["id"]
        )
        assert second_point["total_brew_time_s"] is None
        assert second_point["overall_throughput_g_s"] is None

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
        cancelled = client.post(
            f"/api/v1/brews/{abandoned['id']}/cancel",
            headers=headers,
            json={"revision": abandoned["revision"]},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        repeat_cancel = client.post(
            f"/api/v1/brews/{abandoned['id']}/cancel",
            headers=headers,
            json={"revision": cancelled.json()["revision"]},
        )
        assert repeat_cancel.status_code == 409
        assert repeat_cancel.json()["detail"] == "Only draft brews can be cancelled"
        assert (
            client.post(
                f"/api/v1/brews/{abandoned['id']}/void",
                headers=headers,
                json={"revision": cancelled.json()["revision"]},
            ).status_code
            == 409
        )

        finalized_response = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=headers,
            json={
                "total_brew_time_s": 180,
                "water_g": 242,
                "revision": brew["revision"],
            },
        )
        assert finalized_response.status_code == 200, finalized_response.text
        finalized = finalized_response.json()
        assert finalized["status"] == "completed"
        assert finalized["rating_token"]
        assert finalized["overall_throughput_g_s"] == 1.34
        cancel_completed = client.post(
            f"/api/v1/brews/{brew['id']}/cancel",
            headers=headers,
            json={"revision": finalized["revision"]},
        )
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
            client.post(
                f"/api/v1/brews/{brew['id']}/void",
                headers=member_headers,
                json={"revision": finalized["revision"]},
            ).status_code
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
            json={"total_brew_time_s": 190, "revision": second_brew["revision"]},
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
                f"/api/v1/brews/{second_brew['id']}/void",
                headers=admin_headers,
                json={
                    "revision": client.get(f"/api/v1/brews/{second_brew['id']}").json()["revision"]
                },
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
            json={"revision": corrected.json()["revision"]},
        )
        assert voided.status_code == 200
        repeat_void = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers=admin_headers,
            json={"revision": voided.json()["revision"]},
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
            json={"operator_id": linus["id"], "revision": admin_transfer["revision"]},
        )
        assert admin_reassigned.status_code == 200
        assert admin_reassigned.json()["operator_name"] == "Linus"

        grace_headers = login(grace["id"], "5678")
        brew = client.post("/api/v1/brews", headers=grace_headers, json=brew_input).json()
        missing = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": 99999, "revision": brew["revision"]},
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Operator not found"
        inactive = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": inactive_operator["id"], "revision": brew["revision"]},
        )
        assert inactive.status_code == 422
        assert inactive.json()["detail"] == "Operator must be active"

        linus_headers = login(linus["id"], "6789")
        forbidden = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=linus_headers,
            json={"operator_id": linus["id"], "revision": brew["revision"]},
        )
        assert forbidden.status_code == 403

        grace_headers = login(grace["id"], "5678")
        reassigned = client.put(
            f"/api/v1/brews/{brew['id']}/operator",
            headers=grace_headers,
            json={"operator_id": linus["id"], "revision": brew["revision"]},
        )
        assert reassigned.status_code == 200
        assert reassigned.json()["operator_id"] == linus["id"]
        assert reassigned.json()["operator_name"] == "Linus"
        assert {operator["id"] for operator in reassigned.json()["operators"]} == {
            grace["id"],
            linus["id"],
        }
        edited = client.put(
            f"/api/v1/brews/{brew['id']}",
            headers=grace_headers,
            json={**brew_input, "revision": reassigned.json()["revision"]},
        )
        assert edited.status_code == 200
        assert (
            client.post(
                f"/api/v1/brews/{brew['id']}/cancel",
                headers=grace_headers,
                json={"revision": edited.json()["revision"]},
            ).status_code
            == 403
        )

        linus_headers = login(linus["id"], "6789")
        finalized_response = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=linus_headers,
            json={"total_brew_time_s": 180, "revision": edited.json()["revision"]},
        )
        assert finalized_response.status_code == 200
        finalized = finalized_response.json()
        assert finalized["operator_id"] == linus["id"]
        rating_token = finalized["rating_token"]
        assert (
            client.put(
                f"/api/v1/brews/{brew['id']}/operator",
                headers=linus_headers,
                json={"operator_id": grace["id"], "revision": finalized["revision"]},
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
            client.post(
                f"/api/v1/brews/{brew['id']}/void",
                headers=grace_headers,
                json={"revision": finalized["revision"]},
            ).status_code
            == 403
        )
        analytics = client.get("/api/v1/analytics").json()
        assert analytics["operator_counts"] == [
            {"profile_id": grace["id"], "display_name": "Grace", "brew_count": 1},
            {"profile_id": linus["id"], "display_name": "Linus", "brew_count": 1},
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
            json={"total_brew_time_s": 180, "revision": completed["revision"]},
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
                json={"operator_id": operator_id, "revision": draft["revision"]},
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
