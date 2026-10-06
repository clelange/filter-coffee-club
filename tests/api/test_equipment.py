from __future__ import annotations

from pathlib import Path

from tests.api_helpers import bootstrap, build_client


def test_grinder_definitions_custom_ranges_and_live_conversion(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        c40 = client.get("/api/v1/grinders").json()[0]
        preset = client.get("/api/v1/presets").json()[0]
        initial_count = len(client.get("/api/v1/grinders").json())

        noncanonical_known = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={"definition_key": "kingrinder_k6", "manufacturer": "Override"},
        )
        assert noncanonical_known.status_code == 422
        assert len(client.get("/api/v1/grinders").json()) == initial_count

        k6_response = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={"definition_key": "kingrinder_k6"},
        )
        assert k6_response.status_code == 200
        k6 = k6_response.json()
        assert k6 == {
            **k6,
            "definition_key": "kingrinder_k6",
            "manufacturer": "KINGrinder",
            "model": "K6",
            "setting_unit": "clicks",
            "setting_step": 1.0,
            "soft_min": 15.0,
            "soft_max": 150.0,
        }

        half_filled = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Orbit",
                "model": "One",
                "setting_unit": "clicks",
                "setting_step": 1,
                "preset_ranges": [
                    {"preset_id": preset["id"], "setting_min": 4, "setting_max": None}
                ],
            },
        )
        assert half_filled.status_code == 422
        assert len(client.get("/api/v1/grinders").json()) == initial_count + 1

        reversed_range = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Orbit",
                "model": "One",
                "setting_unit": "clicks",
                "setting_step": 1,
                "preset_ranges": [{"preset_id": preset["id"], "setting_min": 7, "setting_max": 4}],
            },
        )
        assert reversed_range.status_code == 422

        fractional_range = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Orbit",
                "model": "One",
                "setting_unit": "clicks",
                "setting_step": 1,
                "preset_ranges": [
                    {"preset_id": preset["id"], "setting_min": 4.5, "setting_max": 7}
                ],
            },
        )
        assert fractional_range.status_code == 422

        custom_response = client.post(
            "/api/v1/grinders",
            headers=headers,
            json={
                "definition_key": "custom",
                "manufacturer": "Orbit",
                "model": "One",
                "setting_unit": "clicks",
                "setting_step": 1,
                "soft_min": 0,
                "soft_max": 20,
                "guidance": "Zero the burrs first.",
                "preset_ranges": [{"preset_id": preset["id"], "setting_min": 4, "setting_max": 7}],
            },
        )
        assert custom_response.status_code == 200
        custom = custom_response.json()
        assert custom["definition_key"] == "custom"

        effective = client.get("/api/v1/presets").json()[0]
        ranges = {item["grinder_id"]: item for item in effective["grinder_ranges"]}
        assert ranges[c40["id"]] == {
            "grinder_id": c40["id"],
            "setting_min": effective["reference_grinder_range"]["setting_min"],
            "setting_max": effective["reference_grinder_range"]["setting_max"],
            "source": "reference",
        }
        assert ranges[k6["id"]]["source"] == "derived"
        assert ranges[k6["id"]]["setting_min"] == round(
            effective["reference_grinder_range"]["setting_min"] * 3.2
        )
        assert ranges[k6["id"]]["setting_max"] == round(
            effective["reference_grinder_range"]["setting_max"] * 3.2
        )
        assert ranges[custom["id"]] == {
            "grinder_id": custom["id"],
            "setting_min": 4.0,
            "setting_max": 7.0,
            "source": "custom",
        }

        update_payload = {
            key: value
            for key, value in effective.items()
            if key not in {"id", "grinder_ranges", "reference_grinder_range"}
        }
        update_payload["reference_grinder_range"] = {"setting_min": 29, "setting_max": 33}
        update_payload["custom_grinder_ranges"] = [
            {"grinder_id": custom["id"], "setting_min": 4, "setting_max": 7}
        ]
        updated = client.put(
            f"/api/v1/presets/{preset['id']}", headers=headers, json=update_payload
        )
        assert updated.status_code == 200
        updated_ranges = {item["grinder_id"]: item for item in updated.json()["grinder_ranges"]}
        assert updated_ranges[k6["id"]]["setting_min"] == 93
        assert updated_ranges[k6["id"]]["setting_max"] == 106

        update_payload["reference_grinder_range"] = None
        without_reference = client.put(
            f"/api/v1/presets/{preset['id']}", headers=headers, json=update_payload
        )
        assert without_reference.status_code == 200
        assert without_reference.json()["reference_grinder_range"] is None
        assert without_reference.json()["grinder_ranges"] == [
            {
                "grinder_id": custom["id"],
                "setting_min": 4.0,
                "setting_max": 7.0,
                "source": "custom",
            }
        ]

        archived = client.post(f"/api/v1/grinders/{k6['id']}/archive", headers=headers)
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        assert all(item["id"] != k6["id"] for item in client.get("/api/v1/grinders").json())
        direct_archived = client.get(f"/api/v1/grinders/{k6['id']}")
        assert direct_archived.status_code == 200
        assert direct_archived.json()["archived"] is True
