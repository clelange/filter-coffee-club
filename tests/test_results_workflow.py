import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from app.models import Brew, Rating
from app.schemas import BrewInput
from fastapi.testclient import TestClient
from test_api import bootstrap, build_client


def recipe(client: TestClient, headers: dict) -> dict:
    coffee = client.post(
        "/api/v1/coffees", headers=headers, json={"roaster": "Results", "name": "Shared bag"}
    ).json()
    grinder = client.get("/api/v1/grinders").json()[0]
    return {
        "coffee_id": coffee["id"],
        "grinder_id": grinder["id"],
        "dose_g": 20,
        "water_g": 320,
        "temperature_c": 93,
        "grinder_setting": 25,
    }


def member(client: TestClient, headers: dict, name: str) -> int:
    profile = client.post(
        "/api/v1/people",
        headers=headers,
        json={"display_name": name, "pin": "5678", "role": "member"},
    ).json()
    client.put(
        f"/api/v1/people/{profile['id']}", headers=headers, json={"pin_change_required": False}
    )
    return profile["id"]


def finish(client: TestClient, headers: dict, values: dict) -> dict:
    draft = client.post("/api/v1/brews", headers=headers, json=values).json()
    response = client.post(
        f"/api/v1/brews/{draft['id']}/finalize",
        headers=headers,
        json={"revision": draft["revision"], "total_brew_time_s": 180},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_stale_correction_preserves_new_measurements_and_brewers(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        second = member(client, headers, "Second brewer")
        brew = finish(client, headers, values)
        endpoint = f"/api/v1/brews/{brew['id']}/correction"
        original = {**values, "total_brew_time_s": 180, "revision": brew["revision"]}
        changed = client.put(
            endpoint,
            headers=headers,
            json={**original, "temperature_c": 96, "operator_ids": [1, second]},
        )
        assert changed.status_code == 200
        stale = client.put(
            endpoint,
            headers=headers,
            json={**original, "total_brew_time_s": 210, "operator_ids": [1]},
        )
        assert stale.status_code == 409
        saved = client.get(f"/api/v1/brews/{brew['id']}").json()
        assert saved["temperature_c"] == 96
        assert saved["total_brew_time_s"] == 180
        assert {item["id"] for item in saved["operators"]} == {1, second}
        assert (
            client.put(
                endpoint, headers=headers, json={**values, "total_brew_time_s": 180}
            ).status_code
            == 422
        )


def test_pre_upgrade_creation_retries_preserve_the_original_draft(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        second = member(client, headers, "Co-brewer")
        creation_headers = {**headers, "Idempotency-Key": "pre-upgrade-draft"}
        draft = client.post("/api/v1/brews", headers=creation_headers, json=values).json()
        # The previous release hashed BrewInput, before operator_ids existed.
        legacy_request = json.dumps(
            {"payload": BrewInput(**values).model_dump(mode="json"), "profile_id": 1},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        with client.app.state.session_factory() as db:
            db.get(Brew, draft["id"]).creation_request_hash = hashlib.sha256(
                legacy_request.encode()
            ).hexdigest()
            db.commit()
        for crew in ({}, {"operator_ids": None}, {"operator_ids": [1]}):
            retried = client.post(
                "/api/v1/brews", headers=creation_headers, json={**values, **crew}
            )
            assert retried.status_code == 200
            assert retried.json()["id"] == draft["id"]
        changed = client.post(
            "/api/v1/brews",
            headers=creation_headers,
            json={**values, "operator_ids": [1, second]},
        )
        assert changed.status_code == 409
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1


def test_brewers_can_be_selected_removed_at_finish_and_corrected(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        second = member(client, headers, "Co-brewer")
        third = member(client, headers, "Another brewer")
        for ids in ([], [second], [1, second, second]):
            assert (
                client.post(
                    "/api/v1/brews", headers=headers, json={**values, "operator_ids": ids}
                ).status_code
                == 422
            )
        draft = client.post(
            "/api/v1/brews", headers=headers, json={**values, "operator_ids": [second, 1]}
        ).json()
        assert {item["id"] for item in draft["operators"]} == {1, second}
        edited = client.put(
            f"/api/v1/brews/{draft['id']}",
            headers=headers,
            json={**values, "revision": draft["revision"], "operator_ids": [1, third]},
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": second, "pin": "5678", "device_mode": "personal"},
        ).json()
        second_headers = {"X-CSRF-Token": login["csrf_token"]}
        assert (
            client.put(
                f"/api/v1/brews/{draft['id']}",
                headers=second_headers,
                json={**values, "revision": edited["revision"]},
            ).status_code
            == 403
        )
        third_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": third, "pin": "5678", "device_mode": "personal"},
        ).json()
        third_headers = {"X-CSRF-Token": third_login["csrf_token"]}
        assert (
            client.post(
                f"/api/v1/brews/{draft['id']}/finalize",
                headers=third_headers,
                json={
                    "revision": edited["revision"],
                    "total_brew_time_s": 180,
                    "operator_ids": [1],
                },
            ).status_code
            == 403
        )
        admin = client.post(
            "/api/v1/auth/login", json={"profile_id": 1, "pin": "1234", "device_mode": "personal"}
        ).json()
        headers = {"X-CSRF-Token": admin["csrf_token"]}
        finalized = client.post(
            f"/api/v1/brews/{draft['id']}/finalize",
            headers=headers,
            json={
                "revision": edited["revision"],
                "total_brew_time_s": 180,
                "operator_ids": [1, second],
            },
        ).json()
        assert {item["id"] for item in finalized["operators"]} == {1, second}
        corrected = client.put(
            f"/api/v1/brews/{draft['id']}/correction",
            headers=headers,
            json={
                **values,
                "revision": finalized["revision"],
                "total_brew_time_s": 180,
                "operator_ids": [1],
            },
        ).json()
        assert [item["id"] for item in corrected["operators"]] == [1]
        assert client.get("/api/v1/analytics").json()["operator_counts"] == [
            {"profile_id": 1, "display_name": "Ada", "brew_count": 1}
        ]


def test_concurrent_repeat_retries_create_one_draft_and_reserve_one_slot(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        brew = finish(client, headers, values)
        repeat_headers = {**headers, "Idempotency-Key": "repeat-one-attempt"}
        gate = Barrier(2)

        def repeat():
            other = TestClient(client.app)
            other.cookies.update(client.cookies)
            try:
                gate.wait(timeout=10)
                return other.post(f"/api/v1/brews/{brew['id']}/clone", headers=repeat_headers)
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: repeat(), range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        assert responses[0].json()["id"] == responses[1].json()["id"]
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1
        other = client.post("/api/v1/brews", headers=headers, json=values).json()
        assert client.get("/api/v1/brews/active").json()["can_start"] is False
        assert (
            client.post(f"/api/v1/brews/{brew['id']}/clone", headers=repeat_headers).status_code
            == 200
        )
        assert (
            client.post(f"/api/v1/brews/{other['id']}/clone", headers=repeat_headers).status_code
            == 409
        )


def test_inactive_brewers_can_be_retained_or_removed_but_not_added(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        second = member(client, headers, "Former brewer")
        draft = client.post(
            "/api/v1/brews", headers=headers, json={**values, "operator_ids": [1, second]}
        ).json()
        client.put(f"/api/v1/people/{second}", headers=headers, json={"active": False})
        endpoint = f"/api/v1/brews/{draft['id']}"
        retained = client.put(
            endpoint,
            headers=headers,
            json={**values, "revision": draft["revision"], "operator_ids": [1, second]},
        )
        assert retained.status_code == 200
        removed = client.put(
            endpoint,
            headers=headers,
            json={**values, "revision": retained.json()["revision"], "operator_ids": [1]},
        )
        assert removed.status_code == 200
        readded = client.put(
            endpoint,
            headers=headers,
            json={
                **values,
                "revision": removed.json()["revision"],
                "operator_ids": [1, second],
            },
        )
        assert readded.status_code == 422
        saved = client.get(endpoint).json()
        assert saved["revision"] == removed.json()["revision"]
        assert [profile["id"] for profile in saved["operators"]] == [1]


def test_concurrent_brewer_edits_keep_the_winning_measurements_and_membership(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        profiles = [member(client, headers, name) for name in ("Brewer two", "Brewer three")]
        draft = client.post("/api/v1/brews", headers=headers, json=values).json()
        gate = Barrier(2)

        def edit(profile_id: int):
            other = TestClient(client.app)
            other.cookies.update(client.cookies)
            try:
                gate.wait(timeout=10)
                return other.put(
                    f"/api/v1/brews/{draft['id']}",
                    headers=headers,
                    json={
                        **values,
                        "revision": draft["revision"],
                        "operator_ids": [1, profile_id],
                        "temperature_c": 90 + profile_id,
                    },
                )
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(edit, profiles))
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(response.json() for response in responses if response.status_code == 200)
        saved = client.get(f"/api/v1/brews/{draft['id']}").json()
        assert saved["operators"] == winner["operators"]
        assert saved["temperature_c"] == winner["temperature_c"]
        assert saved["revision"] == draft["revision"] + 1
        assert client.get("/api/v1/brews/active").json()["active_count"] == 1


def test_coffee_average_pools_votes_and_best_brew_uses_all_history(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        values = recipe(client, headers)
        second = member(client, headers, "Taster two")
        third = member(client, headers, "Taster three")
        qualified = finish(client, headers, values)
        early = finish(client, headers, {**values, "temperature_c": 96})
        with client.app.state.session_factory() as db:
            for brew_id, profile_id, score in [
                (qualified["id"], 1, 6),
                (qualified["id"], second, 6),
                (qualified["id"], third, 6),
                (early["id"], 1, 9),
            ]:
                db.add(
                    Rating(
                        brew_id=brew_id,
                        profile_id=profile_id,
                        liking=score,
                        acidity=2,
                        bitterness=2,
                        sweetness=3,
                        body=3,
                    )
                )
            db.commit()
        insights = client.get(
            f"/api/v1/coffees/{values['coffee_id']}/rating-insights?limit=1"
        ).json()
        summary = client.get("/api/v1/analytics").json()
        coffee = summary["coffee_summaries"][0]
        assert coffee["average"] == insights["aggregate"]["averages"]["liking"] == 6.75
        assert (coffee["ratings"], coffee["brews"], coffee["tasters"]) == (4, 2, 3)
        assert insights["rated_brews"][0]["brew"]["id"] == early["id"]
        assert (
            insights["best_brew"]["brew"]["id"]
            == coffee["best_brew"]["brew"]["id"]
            == qualified["id"]
        )
        assert summary["top_recipes"][0]["brew_id"] == qualified["id"]
        assert summary["top_coffees"][0]["average"] == 6.75
        # Voiding the qualifying brew removes its ratings from every summary and ranking.
        client.post(
            f"/api/v1/brews/{qualified['id']}/void",
            headers=headers,
            json={"revision": qualified["revision"]},
        )
        summary = client.get("/api/v1/analytics").json()
        assert summary["top_coffees"] == summary["top_recipes"] == []
        assert summary["coffee_summaries"][0]["average"] == 9
        assert summary["coffee_summaries"][0]["best_brew"] is None
