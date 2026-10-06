from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

from app.models import (
    Brew,
    Profile,
)
from app.services import brews as brew_service

from tests.api_helpers import bootstrap, build_client


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
        original_is_brew_operator = brew_service.is_brew_operator

        def synchronized_membership_check(loaded_brew: Brew, profile_id: int) -> bool:
            result = original_is_brew_operator(loaded_brew, profile_id)
            if profile_id == bob["id"] and not result:
                barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(brew_service, "is_brew_operator", synchronized_membership_check)

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
        original_is_brew_operator = brew_service.is_brew_operator

        def pause_join_after_membership_check(loaded_brew: Brew, profile_id: int) -> bool:
            result = original_is_brew_operator(loaded_brew, profile_id)
            if profile_id == bob["id"] and not result and not join_checked.is_set():
                join_checked.set()
                assert allow_join.wait(timeout=5)
            return result

        monkeypatch.setattr(brew_service, "is_brew_operator", pause_join_after_membership_check)

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
            json={
                **correction,
                "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
            },
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
                json={
                    **correction,
                    "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
                },
            ).status_code
            == 403
        )
        grace_headers = login(grace["id"], "5678")
        invalid_correction = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=grace_headers,
            json={
                "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
                **correction,
                "operator_id": inactive_operator["id"],
            },
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
            json={
                **{key: value for key, value in correction.items() if key != "operator_id"},
                "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
            },
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
        original_load_active_operator = brew_service.load_active_operator

        def synchronized_load_active_operator(db, operator_id: int) -> Profile:
            operator = original_load_active_operator(db, operator_id)
            barrier.wait(timeout=5)
            return operator

        monkeypatch.setattr(brew_service, "load_active_operator", synchronized_load_active_operator)

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
                    "revision": client.get(f"/api/v1/brews/{completed['id']}").json()["revision"],
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
