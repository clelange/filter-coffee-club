from __future__ import annotations

from pathlib import Path

from tests.api_helpers import bootstrap, build_client


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
            json={
                "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
                **brew_input,
                "operator_id": bob["id"],
                "total_brew_time_s": 180,
            },
        )

        assert corrected.status_code == 200
        assert corrected.json()["operator_id"] == bob["id"]
        assert corrected.json()["revision"] == completed["revision"] + 1
        assert [operator["display_name"] for operator in corrected.json()["operators"]] == ["Bob"]
        assert client.get("/api/v1/analytics").json()["operator_counts"] == [
            {"profile_id": bob["id"], "display_name": "Bob", "brew_count": 1}
        ]


def test_analytics_preserves_original_settings_and_adds_reference_scale(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees", headers=headers, json={"roaster": "Atlas", "name": "Alpha"}
        ).json()
        c40 = client.get("/api/v1/grinders").json()[0]
        k6 = client.post(
            "/api/v1/grinders", headers=headers, json={"definition_key": "kingrinder_k6"}
        ).json()
        custom = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Orbit",
                "model": "One",
                "setting_unit": "steps",
                "setting_step": 0.25,
            },
        ).json()
        for grinder, setting in [(c40, 28), (k6, 90), (custom, 5.25)]:
            created = client.post(
                "/api/v1/brews",
                headers=headers,
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 92,
                    "grinder_setting": setting,
                },
            )
            assert created.status_code == 200, created.text
            brew = created.json()
            finalized = client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=headers,
                json={"total_brew_time_s": 180, "revision": brew["revision"]},
            )
            assert finalized.status_code == 200, finalized.text
            rating = client.post(
                f"/api/v1/brews/{brew['id']}/ratings",
                headers=headers,
                json={"liking": 7, "acidity": 3, "bitterness": 1, "sweetness": 3, "body": 2},
            )
            assert rating.status_code == 200, rating.text

        response = client.get("/api/v1/analytics")
        assert response.status_code == 200, response.text
        analytics = response.json()
        assert analytics["grinder_definitions"] == client.get("/api/v1/grinder-definitions").json()
        points = {point["grinder_definition_key"]: point for point in analytics["scatter"]}
        assert points["comandante_c40"]["reference_grinder_setting"] == 28
        assert points["kingrinder_k6"]["reference_grinder_setting"] == 28.125
        assert points["kingrinder_k6"]["grinder_setting"] == 90
        assert points["custom"]["reference_grinder_setting"] is None
        assert points["custom"]["grinder_setting"] == 5.25
        assert points["custom"]["grinder_unit"] == "steps"
