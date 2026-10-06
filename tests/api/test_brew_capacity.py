from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from app.models import (
    AppSettings,
    Brew,
)
from app.routers import brews as brews_module
from app.services import brews as brew_service

from tests.api_helpers import bootstrap, build_client, settings_payload


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
        assert client.get("/api/v1/brews?exclude_status=draft").json() == []

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
            brew_detail = client.get(f"/api/v1/brews/{brew['id']}").json()
            cancelled = client.post(
                f"/api/v1/brews/{brew['id']}/cancel",
                headers=headers,
                json={"revision": brew_detail["revision"]},
            )
            assert cancelled.status_code == 200
            state = client.get("/api/v1/brews/active").json()
            assert state["can_start"] is (index == len(drafts) - 1)

        past_brews = client.get("/api/v1/brews?exclude_status=draft").json()
        assert len(past_brews) == 3
        assert {brew["status"] for brew in past_brews} == {"cancelled"}

        replacement = client.post("/api/v1/brews", headers=headers, json=brew_input)
        assert replacement.status_code == 200
        with client.app.state.session_factory() as db:
            assert db.get(AppSettings, 1).active_brew_count == 1


def test_active_brews_include_recent_rating_prompts_for_thirty_minutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(brews_module, "utcnow", lambda: now)

    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Prompt", "name": "Window Lot"},
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

        def start_brew() -> dict:
            response = client.post("/api/v1/brews", headers=headers, json=brew_input)
            assert response.status_code == 200, response.text
            return response.json()

        def finalize_brew(brew: dict) -> dict:
            response = client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": 180, "revision": brew["revision"]},
            )
            assert response.status_code == 200, response.text
            return response.json()

        active_oldest = start_brew()
        boundary = finalize_brew(start_brew())
        older = finalize_brew(start_brew())
        voided = finalize_brew(start_brew())
        assert (
            client.post(
                f"/api/v1/brews/{voided['id']}/void",
                headers=headers,
                json={"revision": voided["revision"]},
            ).status_code
            == 200
        )
        cancelled = start_brew()
        assert (
            client.post(
                f"/api/v1/brews/{cancelled['id']}/cancel",
                headers=headers,
                json={"revision": cancelled["revision"]},
            ).status_code
            == 200
        )
        recent_newer = finalize_brew(start_brew())
        active_newest = start_brew()

        with client.app.state.session_factory() as db:
            boundary_row = db.get(Brew, boundary["id"])
            older_row = db.get(Brew, older["id"])
            recent_newer_row = db.get(Brew, recent_newer["id"])
            assert boundary_row is not None
            assert older_row is not None
            assert recent_newer_row is not None
            boundary_row.completed_at = now - timedelta(minutes=30)
            older_row.completed_at = now - timedelta(minutes=30, seconds=1)
            recent_newer_row.completed_at = now - timedelta(minutes=5)
            db.commit()

        state = client.get("/api/v1/brews/active").json()
        assert [item["id"] for item in state["brews"]] == [
            active_oldest["id"],
            active_newest["id"],
        ]
        assert [item["id"] for item in state["recent_rating_brews"]] == [
            recent_newer["id"],
            boundary["id"],
        ]
        activity_item_fields = {
            "id",
            "coffee_name",
            "coffee_roaster",
            "operators",
            "status",
            "rating_token",
        }
        assert all(set(item) == activity_item_fields for item in state["brews"])
        assert all(set(item) == activity_item_fields for item in state["recent_rating_brews"])
        assert all(item["rating_token"] for item in state["recent_rating_brews"])
        assert state["active_count"] == 2
        assert state["max_active_brews"] == 2
        assert state["can_start"] is False

        old_link = client.get(f"/api/v1/rating-links/{older['rating_token']}").json()
        assert old_link["active"] is True
        assert old_link["brew"]["id"] == older["id"]


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
        original_commit_guarded = brew_service.commit_guarded_brew_update

        def synchronized_commit(*args, **kwargs):
            barrier.wait(timeout=5)
            return original_commit_guarded(*args, **kwargs)

        monkeypatch.setattr(brew_service, "commit_guarded_brew_update", synchronized_commit)

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
