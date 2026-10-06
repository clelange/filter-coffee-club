from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from app.models import (
    Brew,
)
from app.routers import brews as brews_module
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.api_helpers import bootstrap, build_client, settings_payload


def test_brew_creation_is_idempotent_and_profile_scoped(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Orbit", "name": "Single brew"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        payload = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }
        idempotent_headers = {**admin_headers, "Idempotency-Key": "brew-create-test-key"}

        first = client.post("/api/v1/brews", headers=idempotent_headers, json=payload)
        replay = client.post("/api/v1/brews", headers=idempotent_headers, json=payload)

        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["id"] == first.json()["id"]
        assert len(client.get("/api/v1/brews").json()) == 1
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1

        conflict = client.post(
            "/api/v1/brews",
            headers=idempotent_headers,
            json={**payload, "water_g": 250},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"].startswith("Idempotency key was already used")
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1

        edited_payload = {**payload, "grinder_setting": 31, "revision": first.json()["revision"]}
        edited = client.put(
            f"/api/v1/brews/{first.json()['id']}", headers=admin_headers, json=edited_payload
        )
        replay_after_edit = client.post("/api/v1/brews", headers=idempotent_headers, json=payload)
        assert edited.status_code == 200
        assert replay_after_edit.status_code == 200
        assert replay_after_edit.json()["id"] == first.json()["id"]
        assert replay_after_edit.json()["grinder_setting"] == 31

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
        other_profile = client.post(
            "/api/v1/brews",
            headers={
                "X-CSRF-Token": member_session["csrf_token"],
                "Idempotency-Key": "brew-create-test-key",
            },
            json=payload,
        )
        assert other_profile.status_code == 409
        assert len(client.get("/api/v1/brews").json()) == 1


def test_concurrent_brew_creation_with_same_key_uses_one_capacity_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        settings = client.get("/api/v1/settings").json()
        assert (
            client.put(
                "/api/v1/settings",
                headers=headers,
                json=settings_payload(settings, max_active_brews=1),
            ).status_code
            == 200
        )
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Concurrent brew"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        payload = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }
        idempotent_headers = {**headers, "Idempotency-Key": "concurrent-brew-create"}
        barrier = Barrier(2)
        original_enforce_demo_capacity = brews_module.enforce_demo_capacity

        def synchronized_enforce_demo_capacity(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            barrier.wait(timeout=5)
            original_enforce_demo_capacity(*args, **kwargs)

        monkeypatch.setattr(
            brews_module, "enforce_demo_capacity", synchronized_enforce_demo_capacity
        )

        def create_brew(_attempt: int) -> tuple[int, int]:
            response = client.post("/api/v1/brews", headers=idempotent_headers, json=payload)
            return response.status_code, response.json()["id"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create_brew, range(2)))

        assert [status for status, _brew_id in results] == [200, 200]
        assert len({brew_id for _status, brew_id in results}) == 1
        assert len(client.get("/api/v1/brews").json()) == 1
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1


def test_unrelated_brew_integrity_error_is_not_an_idempotency_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Failed brew"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        original_commit = Session.commit

        def fail_brew_commit(db: Session) -> None:
            if any(isinstance(item, Brew) for item in db.new):
                raise IntegrityError("forced statement", {}, RuntimeError("forced brew failure"))
            original_commit(db)

        monkeypatch.setattr(Session, "commit", fail_brew_commit)

        with pytest.raises(IntegrityError, match="forced brew failure"):
            client.post(
                "/api/v1/brews",
                headers={**headers, "Idempotency-Key": "unrelated-brew-error"},
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 94,
                    "grinder_setting": 30,
                },
            )

        assert client.get("/api/v1/brews").json() == []
        assert client.get("/api/v1/brews/active").json()["active_count"] == 0
