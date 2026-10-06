from __future__ import annotations

from pathlib import Path

import pytest

from tests.api_helpers import bootstrap, build_client


def test_final_water_cannot_be_lower_than_recorded_bloom_water(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Bloom", "name": "Consistency"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        payload = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
            "bloom_water_g": 45,
        }

        created = client.post("/api/v1/brews", headers=headers, json=payload).json()
        invalid_finalize = client.post(
            f"/api/v1/brews/{created['id']}/finalize",
            headers=headers,
            json={"water_g": 44, "total_brew_time_s": 180, "revision": created["revision"]},
        )
        assert invalid_finalize.status_code == 422
        assert invalid_finalize.json()["detail"] == "Bloom water must not exceed total water"
        assert client.get(f"/api/v1/brews/{created['id']}").json()["status"] == "draft"

        completed = client.post(
            f"/api/v1/brews/{created['id']}/finalize",
            headers=headers,
            json={"water_g": 240, "total_brew_time_s": 180, "revision": created["revision"]},
        ).json()
        assert completed["bloom_water_g"] == 45


def test_target_ratio_is_persisted_cloned_and_exported(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Ratio", "name": "Intent"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        created = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 7.4,
                "water_g": 120,
                "target_ratio": 16.3,
                "temperature_c": 94,
                "grinder_setting": 30,
            },
        )

        assert created.status_code == 200, created.text
        assert created.json()["target_ratio"] == 16.3
        assert created.json()["ratio"] == 16.22

        clone = client.post(f"/api/v1/brews/{created.json()['id']}/clone", headers=headers)
        assert clone.status_code == 200, clone.text
        assert clone.json()["target_ratio"] == 16.3

        exported = client.get("/api/v1/exports/json").json()["brews"]
        assert {brew["target_ratio"] for brew in exported} == {16.3}


def test_unusual_brew_ratio_requires_confirmation_for_every_measurement_mutation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Guard", "name": "Exceptional recipe"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        payload = {
            "coffee_id": coffee["id"],
            "grinder_id": grinder["id"],
            "dose_g": 8,
            "water_g": 640,
            "temperature_c": 94,
            "grinder_setting": 30,
            "servings": 5,
        }
        idempotent_headers = {**headers, "Idempotency-Key": "unusual-ratio-retry"}

        blocked_create = client.post("/api/v1/brews", headers=idempotent_headers, json=payload)
        assert blocked_create.status_code == 422
        assert "total batch amounts" in blocked_create.json()["detail"]
        assert client.get("/api/v1/brews").json() == []
        assert client.get("/api/v1/brews/active").json()["active_count"] == 0

        confirmed_headers = {**idempotent_headers, "X-Confirm-Unusual-Ratio": "true"}
        created = client.post("/api/v1/brews", headers=confirmed_headers, json=payload).json()
        assert created["ratio"] == 80

        update_payload = {**payload, "water_g": 650, "revision": created["revision"]}
        blocked_update = client.put(
            f"/api/v1/brews/{created['id']}", headers=headers, json=update_payload
        )
        assert blocked_update.status_code == 422
        unchanged = client.get(f"/api/v1/brews/{created['id']}").json()
        assert unchanged["water_g"] == 640
        assert unchanged["revision"] == created["revision"]

        updated = client.put(
            f"/api/v1/brews/{created['id']}",
            headers={**headers, "X-Confirm-Unusual-Ratio": "true"},
            json=update_payload,
        ).json()
        assert updated["water_g"] == 650

        confirmed_log_count = caplog.messages.count("unusual_brew_ratio_confirmed")
        stale_confirmed_update = client.put(
            f"/api/v1/brews/{created['id']}",
            headers={**headers, "X-Confirm-Unusual-Ratio": "true"},
            json={**update_payload, "revision": created["revision"]},
        )
        assert stale_confirmed_update.status_code == 409
        assert caplog.messages.count("unusual_brew_ratio_confirmed") == confirmed_log_count

        finalize_payload = {
            "water_g": 655,
            "total_brew_time_s": 180,
            "revision": updated["revision"],
        }
        blocked_finalize = client.post(
            f"/api/v1/brews/{created['id']}/finalize",
            headers=headers,
            json=finalize_payload,
        )
        assert blocked_finalize.status_code == 422
        unchanged = client.get(f"/api/v1/brews/{created['id']}").json()
        assert unchanged["status"] == "draft"
        assert unchanged["water_g"] == 650
        assert unchanged["revision"] == updated["revision"]

        completed = client.post(
            f"/api/v1/brews/{created['id']}/finalize",
            headers={**headers, "X-Confirm-Unusual-Ratio": "true"},
            json=finalize_payload,
        ).json()
        assert completed["status"] == "completed"
        assert completed["water_g"] == 655

        correction_payload = {**payload, "water_g": 660, "total_brew_time_s": 181}
        blocked_correction = client.put(
            f"/api/v1/brews/{created['id']}/correction",
            headers=headers,
            json={
                **correction_payload,
                "revision": client.get(f"/api/v1/brews/{created['id']}").json()["revision"],
            },
        )
        assert blocked_correction.status_code == 422
        unchanged = client.get(f"/api/v1/brews/{created['id']}").json()
        assert unchanged["water_g"] == 655
        assert unchanged["revision"] == completed["revision"]

        corrected = client.put(
            f"/api/v1/brews/{created['id']}/correction",
            headers={**headers, "X-Confirm-Unusual-Ratio": "true"},
            json={
                **correction_payload,
                "revision": client.get(f"/api/v1/brews/{created['id']}").json()["revision"],
            },
        ).json()
        assert corrected["water_g"] == 660
        assert corrected["ratio"] == 82.5
        assert corrected["total_brew_time_s"] == 181
        brew_log_records = [record for record in caplog.records if record.name == "fcc.brew"]
        confirmed_records = [
            record
            for record in brew_log_records
            if record.message == "unusual_brew_ratio_confirmed"
        ]
        assert [getattr(record, "fields")["action"] for record in confirmed_records] == [
            "create",
            "update",
            "finalize",
            "correct",
        ]
        assert all(
            getattr(record, "fields")["brew_id"] == created["id"] for record in confirmed_records
        )
        assert "unusual_brew_ratio_blocked" in caplog.messages


@pytest.mark.parametrize(("dose_g", "water_g"), [(10, 100), (10, 250)])
def test_normal_brew_ratio_boundaries_do_not_require_confirmation(
    tmp_path: Path, dose_g: float, water_g: float
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Boundary", "name": f"Ratio {water_g / dose_g:g}"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        response = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": dose_g,
                "water_g": water_g,
                "temperature_c": 94,
                "grinder_setting": 30,
            },
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize(("dose_g", "water_g"), [(500, 4999), (10, 250.01)])
def test_ratios_just_outside_boundaries_require_confirmation(
    tmp_path: Path, dose_g: float, water_g: float
) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Boundary", "name": f"Outside {water_g / dose_g:g}"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]
        response = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": dose_g,
                "water_g": water_g,
                "temperature_c": 94,
                "grinder_setting": 30,
            },
        )
        assert response.status_code == 422
        assert f"1:{water_g / dose_g:g}" in response.json()["detail"]
