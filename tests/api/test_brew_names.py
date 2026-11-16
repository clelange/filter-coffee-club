from __future__ import annotations

from pathlib import Path

from tests.api_helpers import bootstrap, build_client


def test_brew_names_distinguish_recipes_and_survive_the_brew_lifecycle(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        coffee = client.post(
            "/api/v1/coffees",
            headers=headers,
            json={"roaster": "Orbit", "name": "Same bag"},
        ).json()
        recipe = {
            "coffee_id": coffee["id"],
            "grinder_id": client.get("/api/v1/grinders").json()[0]["id"],
            "dose_g": 15,
            "water_g": 240,
            "temperature_c": 94,
            "grinder_setting": 30,
        }
        too_long = client.post(
            "/api/v1/brews", headers=headers, json={**recipe, "brew_name": "x" * 81}
        )
        assert too_long.status_code == 422

        idempotent_headers = {**headers, "Idempotency-Key": "named-brew-retry"}
        first = client.post(
            "/api/v1/brews", headers=idempotent_headers, json={**recipe, "brew_name": " V60 "}
        )
        assert first.status_code == 200, first.text
        draft = first.json()
        replay = client.post(
            "/api/v1/brews", headers=idempotent_headers, json={**recipe, "brew_name": "V60"}
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == draft["id"]
        conflict = client.post(
            "/api/v1/brews", headers=idempotent_headers, json={**recipe, "brew_name": "Kalita"}
        )
        assert conflict.status_code == 409

        second = client.post(
            "/api/v1/brews", headers=headers, json={**recipe, "brew_name": "Kalita"}
        )
        assert second.status_code == 200, second.text
        active = client.get("/api/v1/brews/active").json()["brews"]
        assert {brew["id"]: brew["brew_name"] for brew in active} == {
            draft["id"]: "V60",
            second.json()["id"]: "Kalita",
        }
        assert {brew["coffee_name"] for brew in active} == {"Same bag"}

        path = f"/api/v1/brews/{draft['id']}"
        # An older client editing the recipe doesn't send a name field.
        edit = client.put(path, headers=headers, json={**recipe, "revision": draft["revision"]})
        assert edit.status_code == 200, edit.text
        assert edit.json()["brew_name"] == "V60"
        finish = client.post(
            f"{path}/finalize",
            headers=headers,
            json={"total_brew_time_s": 180, "revision": edit.json()["revision"]},
        )
        assert finish.status_code == 200, finish.text
        completed = finish.json()
        assert completed["brew_name"] == "V60"

        correction = {**recipe, "total_brew_time_s": 181, "revision": completed["revision"]}
        preserved = client.put(f"{path}/correction", headers=headers, json=correction)
        assert preserved.status_code == 200, preserved.text
        assert preserved.json()["brew_name"] == "V60"
        renamed = client.put(
            f"{path}/correction",
            headers=headers,
            json={
                **correction,
                "revision": preserved.json()["revision"],
                "brew_name": "V60 control",
            },
        )
        assert renamed.status_code == 200, renamed.text
        assert client.get(path).json()["brew_name"] == "V60 control"
        invitation = client.get(f"/api/v1/rating-links/{completed['rating_token']}").json()["brew"]
        assert (invitation["brew_name"], invitation["coffee_name"]) == ("V60 control", "Same bag")
        assert client.get("/api/v1/brews/active").json()["recent_rating_brews"][0]["brew_name"] == (
            "V60 control"
        )
        exported = client.get("/api/v1/exports/json").json()["brews"]
        assert {brew["id"]: brew["brew_name"] for brew in exported}[draft["id"]] == "V60 control"

        clone = client.post(f"{path}/clone", headers=headers)
        assert clone.status_code == 200, clone.text
        assert clone.json()["brew_name"] is None

        cleared = client.put(
            f"{path}/correction",
            headers=headers,
            json={**correction, "revision": renamed.json()["revision"], "brew_name": "   "},
        )
        assert cleared.status_code == 200, cleared.text
        assert client.get(path).json()["brew_name"] is None
