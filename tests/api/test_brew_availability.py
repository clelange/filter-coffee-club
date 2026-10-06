from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from app.models import (
    Coffee,
)
from app.services import brews as brew_service
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from tests.api_helpers import bootstrap, build_client


def test_finished_coffee_blocks_new_brews_but_not_existing_draft_edits(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees", headers=headers, json={"roaster": "Orbit", "name": "Last bag"}
        ).json()
        other_coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Already empty"},
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
        draft = client.post("/api/v1/brews", headers=headers, json=brew_input).json()
        client.post(f"/api/v1/coffees/{coffee['id']}/finish", headers=headers)
        client.post(f"/api/v1/coffees/{other_coffee['id']}/finish", headers=headers)

        unavailable_create = client.post("/api/v1/brews", headers=headers, json=brew_input)
        assert unavailable_create.status_code == 409
        assert unavailable_create.json()["detail"] == {
            "code": "coffee_unavailable",
            "message": "Coffee is no longer available for brewing",
        }
        unavailable_clone = client.post(
            f"/api/v1/brews/{draft['id']}/clone", headers=headers, json={}
        )
        assert unavailable_clone.status_code == 409
        unavailable_switch = client.put(
            f"/api/v1/brews/{draft['id']}",
            headers=headers,
            json={
                **brew_input,
                "coffee_id": other_coffee["id"],
                "revision": draft["revision"],
            },
        )
        assert unavailable_switch.status_code == 409

        edited = client.put(
            f"/api/v1/brews/{draft['id']}",
            headers=headers,
            json={**brew_input, "grinder_setting": 31, "revision": draft["revision"]},
        )
        assert edited.status_code == 200
        assert edited.json()["grinder_setting"] == 31


def test_brew_finalization_and_coffee_completion_are_atomic(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees", headers=headers, json={"roaster": "Orbit", "name": "Last bag"}
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
        draft = client.post("/api/v1/brews", headers=headers, json=brew_input).json()
        edited = client.put(
            f"/api/v1/brews/{draft['id']}",
            headers=headers,
            json={**brew_input, "grinder_setting": 31, "revision": draft["revision"]},
        ).json()

        failed_finalize = client.post(
            f"/api/v1/brews/{draft['id']}/finalize",
            headers=headers,
            json={
                "water_g": 238,
                "total_brew_time_s": 180,
                "revision": draft["revision"],
                "mark_coffee_finished": True,
            },
        )
        assert failed_finalize.status_code == 409
        assert client.get(f"/api/v1/coffees/{coffee['id']}").json()["finished_at"] is None
        assert client.get(f"/api/v1/brews/{draft['id']}").json()["status"] == "draft"

        finalized = client.post(
            f"/api/v1/brews/{draft['id']}/finalize",
            headers=headers,
            json={
                "water_g": 238,
                "total_brew_time_s": 180,
                "revision": edited["revision"],
                "mark_coffee_finished": True,
            },
        )
        assert finalized.status_code == 200
        assert finalized.json()["status"] == "completed"
        finalized_coffee = client.get(f"/api/v1/coffees/{coffee['id']}").json()
        assert finalized_coffee["finished_at"] is not None
        assert finalized_coffee["available"] is False


def finish_before_availability_reservation(
    client: TestClient,
    headers: dict[str, str],
    coffee_id: int,
    monkeypatch: pytest.MonkeyPatch,
    action: Callable[[], Response],
) -> Response:
    reservation_started = Event()
    continue_reservation = Event()
    original_reservation = brew_service.reserve_available_coffee

    def paused_reservation(db: Session, target_id: int) -> Coffee:
        if target_id == coffee_id:
            reservation_started.set()
            assert continue_reservation.wait(timeout=5)
        return original_reservation(db, target_id)

    monkeypatch.setattr(brew_service, "reserve_available_coffee", paused_reservation)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending_action = executor.submit(action)
            assert reservation_started.wait(timeout=5)
            finished = client.post(f"/api/v1/coffees/{coffee_id}/finish", headers=headers)
            assert finished.status_code == 200
            continue_reservation.set()
            return pending_action.result(timeout=5)
    finally:
        continue_reservation.set()
        monkeypatch.setattr(brew_service, "reserve_available_coffee", original_reservation)


def test_finishing_coffee_wins_races_with_new_brew_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        grinder = client.get("/api/v1/grinders").json()[0]

        def create_coffee(name: str) -> dict:
            return client.post(
                "/api/v1/coffees",
                headers=headers,
                json={"roaster": "Race", "name": name},
            ).json()

        def brew_input(coffee_id: int) -> dict:
            return {
                "coffee_id": coffee_id,
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30,
            }

        create_target = create_coffee("Create target")
        blocked_create = finish_before_availability_reservation(
            client,
            headers,
            create_target["id"],
            monkeypatch,
            lambda: client.post(
                "/api/v1/brews", headers=headers, json=brew_input(create_target["id"])
            ),
        )
        assert blocked_create.status_code == 409

        source_coffee = create_coffee("Clone source")
        source_input = brew_input(source_coffee["id"])
        source = client.post("/api/v1/brews", headers=headers, json=source_input).json()
        blocked_clone = finish_before_availability_reservation(
            client,
            headers,
            source_coffee["id"],
            monkeypatch,
            lambda: client.post(f"/api/v1/brews/{source['id']}/clone", headers=headers),
        )
        assert blocked_clone.status_code == 409

        switch_target = create_coffee("Switch target")
        blocked_switch = finish_before_availability_reservation(
            client,
            headers,
            switch_target["id"],
            monkeypatch,
            lambda: client.put(
                f"/api/v1/brews/{source['id']}",
                headers=headers,
                json={
                    **source_input,
                    "coffee_id": switch_target["id"],
                    "revision": source["revision"],
                },
            ),
        )
        assert blocked_switch.status_code == 409
