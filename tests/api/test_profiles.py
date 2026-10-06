from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from app.models import (
    Profile,
)
from app.routers import profiles as profiles_module
from app.schemas import ProfileUpdate
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.api_helpers import bootstrap, build_client


def test_profile_changes_must_preserve_an_active_administrator(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        session, headers = bootstrap(client)
        administrator_id = session["profile"]["id"]

        for payload in ({"role": "member"}, {"active": False}):
            response = client.put(
                f"/api/v1/people/{administrator_id}",
                headers=headers,
                json=payload,
            )
            assert response.status_code == 409
            assert response.json()["detail"] == "At least one active administrator must remain"

        second_admin = client.post(
            "/api/v1/people",
            headers=headers,
            json={"display_name": "Grace", "pin": "5678", "role": "admin"},
        ).json()
        demoted = client.put(
            f"/api/v1/people/{administrator_id}",
            headers=headers,
            json={"role": "member"},
        )
        assert demoted.status_code == 200
        assert demoted.json()["role"] == "member"
        assert second_admin["role"] == "admin"


def test_concurrent_profile_changes_preserve_an_active_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with build_client(tmp_path) as client:
        session, headers = bootstrap(client)
        first_admin_id = session["profile"]["id"]
        second_admin_id = client.post(
            "/api/v1/people",
            headers=headers,
            json={"display_name": "Grace", "pin": "5678", "role": "admin"},
        ).json()["id"]
        barrier = Barrier(2)
        original_reserve = profiles_module.reserve_admin_removal

        def synchronized_reserve(db: Session, profile_id: int, payload: ProfileUpdate) -> None:
            barrier.wait(timeout=10)
            original_reserve(db, profile_id, payload)

        monkeypatch.setattr(profiles_module, "reserve_admin_removal", synchronized_reserve)

        def demote(profile_id: int) -> int:
            return client.put(
                f"/api/v1/people/{profile_id}", headers=headers, json={"role": "member"}
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(demote, [first_admin_id, second_admin_id]))

        assert sorted(statuses) == [200, 409]
        with client.app.state.session_factory() as db:
            active_admin_count = db.scalar(
                select(func.count(Profile.id)).where(
                    Profile.role == "admin", Profile.active.is_(True)
                )
            )
        assert active_admin_count == 1


def test_member_directory_visibility_and_account_filtering(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        profiles = {}
        for name, pin in (
            ("Grace", "5678"),
            ("Linus", "6789"),
            ("Inactive", "7890"),
            ("Pending", "8901"),
        ):
            profiles[name] = client.post(
                "/api/v1/people",
                headers=admin_headers,
                json={"display_name": name, "pin": pin, "role": "member"},
            ).json()
        for name in ("Grace", "Linus"):
            assert (
                client.put(
                    f"/api/v1/people/{profiles[name]['id']}",
                    headers=admin_headers,
                    json={"pin_change_required": False},
                ).status_code
                == 200
            )
        assert (
            client.put(
                f"/api/v1/people/{profiles['Inactive']['id']}",
                headers=admin_headers,
                json={"active": False},
            ).status_code
            == 200
        )

        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Directory", "name": "Shared Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        def completed_brew(setting: int) -> dict:
            brew = client.post(
                "/api/v1/brews",
                headers=admin_headers,
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 94,
                    "grinder_setting": setting,
                },
            ).json()
            return client.post(
                f"/api/v1/brews/{brew['id']}/finalize",
                headers=admin_headers,
                json={"total_brew_time_s": 180, "revision": brew["revision"]},
            ).json()

        shared_brew = completed_brew(20)
        grace_brew = completed_brew(21)
        linus_brew = completed_brew(22)
        voided_brew = completed_brew(23)
        rating_payload = {
            "liking": 7,
            "acidity": 3,
            "bitterness": 2,
            "sweetness": 4,
            "body": 3,
            "flavor_tag_ids": [],
        }
        for brew in (shared_brew, grace_brew, linus_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=admin_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )

        def login(name: str, pin: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "profile_id": profiles[name]["id"],
                    "pin": pin,
                    "device_mode": "personal",
                },
            )
            assert response.status_code == 200, response.text
            return {"X-CSRF-Token": response.json()["csrf_token"]}

        grace_headers = login("Grace", "5678")
        for brew in (shared_brew, grace_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=grace_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )
        linus_headers = login("Linus", "6789")
        for brew in (shared_brew, linus_brew, voided_brew):
            assert (
                client.post(
                    f"/api/v1/brews/{brew['id']}/ratings",
                    headers=linus_headers,
                    json=rating_payload,
                ).status_code
                == 200
            )

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        assert (
            client.post(
                f"/api/v1/brews/{voided_brew['id']}/void",
                headers=admin_headers,
                json={"revision": voided_brew["revision"]},
            ).status_code
            == 200
        )

        login("Grace", "5678")
        member_directory = client.get("/api/v1/profiles")
        assert member_directory.status_code == 200
        member_items = member_directory.json()
        assert [item["display_name"] for item in member_items] == [
            "Ada",
            "Grace",
            "Linus",
            "Pending",
        ]
        assert all(
            set(item)
            == {
                "id",
                "display_name",
                "is_self",
                "is_complete_history",
                "rating_count",
            }
            for item in member_items
        )
        member_by_name = {item["display_name"]: item for item in member_items}
        assert member_by_name["Grace"] == {
            "id": profiles["Grace"]["id"],
            "display_name": "Grace",
            "is_self": True,
            "is_complete_history": True,
            "rating_count": 2,
        }
        assert member_by_name["Ada"]["rating_count"] == 2
        assert member_by_name["Linus"]["rating_count"] == 1
        assert member_by_name["Linus"]["is_complete_history"] is False
        assert member_by_name["Pending"]["rating_count"] == 0

        client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        )
        admin_items = client.get("/api/v1/profiles").json()
        admin_by_name = {item["display_name"]: item for item in admin_items}
        assert all(item["is_complete_history"] for item in admin_items)
        assert admin_by_name["Ada"]["rating_count"] == 3
        assert admin_by_name["Grace"]["rating_count"] == 2
        assert admin_by_name["Linus"]["rating_count"] == 2

        login("Pending", "8901")
        assert client.get("/api/v1/profiles").status_code == 403
        pending_session = client.get("/api/v1/auth/me").json()
        pending_headers = {"X-CSRF-Token": pending_session["csrf_token"]}
        assert client.post("/api/v1/auth/logout", headers=pending_headers).status_code == 204
        assert client.get("/api/v1/profiles").status_code == 401
