from __future__ import annotations

from pathlib import Path

from tests.api_helpers import bootstrap, build_client


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
