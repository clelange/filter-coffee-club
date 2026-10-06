from __future__ import annotations

from pathlib import Path

from app.models import (
    Brew,
)

from tests.api_helpers import bootstrap, build_client


def test_coffee_and_brew_rating_insights(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, admin_headers = bootstrap(client)
        member = client.post(
            "/api/v1/people",
            headers=admin_headers,
            json={"display_name": "Grace", "pin": "5678", "role": "member"},
        ).json()
        coffee = client.post(
            "/api/v1/coffees",
            headers=admin_headers,
            json={"roaster": "Insight Roasters", "name": "Weighted Lot"},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        def completed_brew(setting: int) -> dict:
            created = client.post(
                "/api/v1/brews",
                headers=admin_headers,
                json={
                    "coffee_id": coffee["id"],
                    "grinder_id": grinder["id"],
                    "dose_g": 15,
                    "water_g": 240,
                    "temperature_c": 92,
                    "grinder_setting": setting,
                },
            ).json()
            finalized = client.post(
                f"/api/v1/brews/{created['id']}/finalize",
                headers=admin_headers,
                json={"total_brew_time_s": 180 + setting, "revision": created["revision"]},
            )
            assert finalized.status_code == 200, finalized.text
            return finalized.json()

        first_brew = completed_brew(20)
        second_brew = completed_brew(21)
        unrated_brew = completed_brew(22)
        voided_brew = completed_brew(23)
        draft_brew = client.post(
            "/api/v1/brews",
            headers=admin_headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 92,
                "grinder_setting": 24,
            },
        ).json()

        tags = client.get("/api/v1/flavor-tags?active_only=false").json()
        fruity = next(tag for tag in tags if tag["name"] == "Fruity" and tag["parent_id"] is None)
        fruity_child = next(tag for tag in tags if tag["parent_id"] == fruity["id"])

        def submit_rating(brew: dict, payload: dict, headers: dict[str, str]) -> None:
            response = client.post(
                f"/api/v1/brews/{brew['id']}/ratings", headers=headers, json=payload
            )
            assert response.status_code == 200, response.text

        submit_rating(
            first_brew,
            {
                "liking": 9,
                "acidity": 5,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [fruity["id"], fruity_child["id"]],
            },
            admin_headers,
        )
        submit_rating(
            second_brew,
            {
                "liking": 3,
                "acidity": 1,
                "bitterness": 5,
                "sweetness": 1,
                "body": 1,
                "flavor_tag_ids": [],
            },
            admin_headers,
        )
        submit_rating(
            voided_brew,
            {
                "liking": 1,
                "acidity": 1,
                "bitterness": 5,
                "sweetness": 0,
                "body": 1,
                "flavor_tag_ids": [fruity["id"]],
            },
            admin_headers,
        )
        assert (
            client.post(
                f"/api/v1/brews/{voided_brew['id']}/void",
                headers=admin_headers,
                json={"revision": voided_brew["revision"]},
            ).status_code
            == 200
        )

        client.post("/api/v1/auth/logout", headers=admin_headers)
        assert client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").status_code == 401
        assert client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert login.json()["profile"]["pin_change_required"] is True
        assert client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").status_code == 403
        assert client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights").status_code == 403
        assert (
            client.post(
                "/api/v1/auth/pin",
                headers=member_headers,
                json={"current_pin": "5678", "new_pin": "6789"},
            ).status_code
            == 204
        )

        visible_without_own_rating = client.get(f"/api/v1/brews/{first_brew['id']}/rating-insights")
        assert visible_without_own_rating.status_code == 200
        assert visible_without_own_rating.json()["count"] == 1
        assert client.get(f"/api/v1/brews/{draft_brew['id']}/rating-insights").status_code == 409
        assert client.get("/api/v1/coffees/99999/rating-insights").status_code == 404

        submit_rating(
            first_brew,
            {
                "liking": 7,
                "acidity": 3,
                "bitterness": 3,
                "sweetness": 2,
                "body": 5,
                "flavor_tag_ids": [fruity_child["id"]],
            },
            member_headers,
        )

        with client.app.state.session_factory() as db:
            legacy_brew = db.get(Brew, second_brew["id"])
            assert legacy_brew is not None
            legacy_brew.total_brew_time_s = None
            db.commit()

        analytics_response = client.get("/api/v1/analytics")
        assert analytics_response.status_code == 200, analytics_response.text
        analytics = analytics_response.json()
        assert analytics["counts"] == {"brews": 3, "ratings": 3, "coffees": 1}
        assert {point["brew_id"] for point in analytics["scatter"]} == {
            first_brew["id"],
            second_brew["id"],
        }
        first_point = next(
            point for point in analytics["scatter"] if point["brew_id"] == first_brew["id"]
        )
        assert first_point["coffee_color"] == coffee["chart_color"]
        assert first_point["liking"] == 8
        assert first_point["ratings"] == 2
        assert first_point["rating_metrics"] == {
            "liking": {"average": 8, "minimum": 7, "maximum": 9},
            "acidity": {"average": 4, "minimum": 3, "maximum": 5},
            "bitterness": {"average": 2, "minimum": 1, "maximum": 3},
            "sweetness": {"average": 3, "minimum": 2, "maximum": 4},
            "body": {"average": 4, "minimum": 3, "maximum": 5},
        }
        assert first_point["grinder_unit"] == "clicks"
        assert first_point["grinder_definition_key"] == "comandante_c40"
        assert first_point["reference_grinder_setting"] == first_point["grinder_setting"]
        assert first_point["target_flow_g_s"] is None
        assert first_point["overall_throughput_g_s"] == 1.2
        second_point = next(
            point for point in analytics["scatter"] if point["brew_id"] == second_brew["id"]
        )
        assert second_point["total_brew_time_s"] is None
        assert second_point["overall_throughput_g_s"] is None

        first_page = client.get(
            f"/api/v1/coffees/{coffee['id']}/rating-insights?limit=1&offset=0"
        ).json()
        assert first_page["rated_brew_count"] == 2
        assert first_page["next_offset"] == 1
        assert [item["brew"]["id"] for item in first_page["rated_brews"]] == [second_brew["id"]]
        assert first_page["rated_brews"][0]["brew"]["rating_token"] is None
        assert "ratings" not in first_page["rated_brews"][0]
        assert "profile" not in first_page["rated_brews"][0]
        assert first_page["aggregate"]["count"] == 3
        assert first_page["aggregate"]["averages"] == {
            "liking": 6.33,
            "acidity": 3,
            "bitterness": 3,
            "sweetness": 2.33,
            "body": 3,
        }
        coffee_fruity = next(
            axis for axis in first_page["aggregate"]["flavor_axes"] if axis["label"] == "Fruity"
        )
        assert coffee_fruity == {
            "id": fruity["id"],
            "label": "Fruity",
            "mentions": 2,
            "total": 3,
        }

        second_page = client.get(
            f"/api/v1/coffees/{coffee['id']}/rating-insights?limit=1&offset=1"
        ).json()
        assert second_page["next_offset"] is None
        assert [item["brew"]["id"] for item in second_page["rated_brews"]] == [first_brew["id"]]
        assert second_page["aggregate"] == first_page["aggregate"]
        first_brew_aggregate = second_page["rated_brews"][0]["aggregate"]
        assert first_brew_aggregate["averages"] == {
            "liking": 8,
            "acidity": 4,
            "bitterness": 2,
            "sweetness": 3,
            "body": 4,
        }
        first_brew_fruity = next(
            axis for axis in first_brew_aggregate["flavor_axes"] if axis["label"] == "Fruity"
        )
        assert first_brew_fruity["mentions"] == 2
        assert first_brew_fruity["total"] == 2

        empty_aggregate = client.get(f"/api/v1/brews/{unrated_brew['id']}/rating-insights").json()
        assert empty_aggregate["count"] == 0
        assert empty_aggregate["averages"] == {}
        assert all(
            axis["mentions"] == 0 and axis["total"] == 0 for axis in empty_aggregate["flavor_axes"]
        )

        client.post("/api/v1/auth/logout", headers=member_headers)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}

        def update_tag(
            tag: dict, *, active: bool | None = None, sort_order: int | None = None
        ) -> None:
            response = client.put(
                f"/api/v1/flavor-tags/{tag['id']}",
                headers=admin_headers,
                json={
                    "name": tag["name"],
                    "parent_id": tag["parent_id"],
                    "active": tag["active"] if active is None else active,
                    "sort_order": tag["sort_order"] if sort_order is None else sort_order,
                },
            )
            assert response.status_code == 200, response.text

        reordered_parent = next(
            tag for tag in reversed(tags) if tag["parent_id"] is None and tag["id"] != fruity["id"]
        )
        update_tag(reordered_parent, sort_order=-1)
        reordered = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert reordered["aggregate"]["flavor_axes"][0]["id"] == reordered_parent["id"]
        update_tag(reordered_parent, sort_order=reordered_parent["sort_order"])

        update_tag(fruity_child, active=False)
        historical_child = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        historical_fruity = next(
            axis
            for axis in historical_child["aggregate"]["flavor_axes"]
            if axis["label"] == "Fruity"
        )
        assert historical_fruity["mentions"] == 2

        update_tag(fruity, active=False)
        inactive_axis = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert "Fruity" not in {axis["label"] for axis in inactive_axis["aggregate"]["flavor_axes"]}
        for parent in (
            tag for tag in tags if tag["parent_id"] is None and tag["id"] != fruity["id"]
        ):
            update_tag(parent, active=False)
        no_axes = client.get(f"/api/v1/coffees/{coffee['id']}/rating-insights").json()
        assert no_axes["aggregate"]["flavor_axes"] == []


def test_brew_qr_and_rating_visibility(tmp_path: Path) -> None:
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
            json={"roaster": "PSI Roasters", "name": "Collider Blend"},
        ).json()
        dripper = client.post(
            "/api/v1/drippers",
            headers=headers,
            json={"manufacturer": "Hario", "model": "V60", "notes": None},
        ).json()
        brew_filter = client.post(
            "/api/v1/filters",
            headers=headers,
            json={"name": "V60 paper 02", "notes": None},
        ).json()
        grinder = client.get("/api/v1/grinders").json()[0]

        fractional_clicks = client.post(
            "/api/v1/brews",
            headers=headers,
            json={
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 94,
                "grinder_setting": 30.5,
            },
        )
        assert fractional_clicks.status_code == 422
        assert fractional_clicks.json()["detail"] == "Grinder click settings must be whole numbers"

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
                "temperature_c": 94,
                "grinder_setting": 30,
                "servings": 2,
                "target_flow_g_s": 4.5,
                "bloom_water_g": 45,
                "bloom_time_s": 30,
                "pour_count": 3,
            },
        ).json()
        assert brew["ratio"] == 16

        abandoned = client.post(f"/api/v1/brews/{brew['id']}/clone", headers=headers).json()
        cancelled = client.post(
            f"/api/v1/brews/{abandoned['id']}/cancel",
            headers=headers,
            json={"revision": abandoned["revision"]},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        repeat_cancel = client.post(
            f"/api/v1/brews/{abandoned['id']}/cancel",
            headers=headers,
            json={"revision": cancelled.json()["revision"]},
        )
        assert repeat_cancel.status_code == 409
        assert repeat_cancel.json()["detail"] == "Only draft brews can be cancelled"
        assert (
            client.post(
                f"/api/v1/brews/{abandoned['id']}/void",
                headers=headers,
                json={"revision": cancelled.json()["revision"]},
            ).status_code
            == 409
        )

        finalized_response = client.post(
            f"/api/v1/brews/{brew['id']}/finalize",
            headers=headers,
            json={
                "total_brew_time_s": 180,
                "water_g": 242,
                "revision": brew["revision"],
            },
        )
        assert finalized_response.status_code == 200, finalized_response.text
        finalized = finalized_response.json()
        assert finalized["status"] == "completed"
        assert finalized["rating_token"]
        assert finalized["overall_throughput_g_s"] == 1.34
        cancel_completed = client.post(
            f"/api/v1/brews/{brew['id']}/cancel",
            headers=headers,
            json={"revision": finalized["revision"]},
        )
        assert cancel_completed.status_code == 409
        assert cancel_completed.json()["detail"] == "Only draft brews can be cancelled"

        link = client.get(f"/api/v1/rating-links/{finalized['rating_token']}").json()
        assert link["active"] is True
        qr = client.get(f"/api/v1/brews/{brew['id']}/qr.svg")
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")
        assert b'width="328"' in qr.content
        assert client.get("/api/v1/settings").json()["public_base_url"] == "http://fcc.test"

        fruity = next(
            item
            for item in client.get("/api/v1/flavor-tags").json()
            if item["name"] == "Fruity" and item["parent_id"] is None
        )
        admin_rating = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=headers,
            json={
                "liking": 7,
                "acidity": 4,
                "bitterness": 2,
                "sweetness": 3,
                "body": 4,
                "flavor_tag_ids": [fruity["id"]],
            },
        )
        assert admin_rating.status_code == 200
        admin_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert set(admin_profile["profile"]) == {"id", "display_name"}
        assert admin_profile["is_self"] is True
        assert admin_profile["is_complete_history"] is True
        assert admin_profile["rating_count"] == 1
        assert admin_profile["favorite_coffees"][0]["average_liking"] == 7
        admin_comparison = admin_profile["ratings"][0]
        assert admin_comparison["selected_flavors"] == ["Fruity"]
        assert admin_comparison["peer_count"] == 0
        assert admin_comparison["peer_averages"] == {}
        assert admin_comparison["peer_deltas"] == {}
        assert admin_profile["next_offset"] is None

        client.post("/api/v1/auth/logout", headers=headers)
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/profiles/1/ratings").status_code == 401
        assert client.get(f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}").status_code == 401
        assert client.get(f"/api/v1/rating-links/{finalized['rating_token']}").status_code == 200
        assert client.get("/api/v1/rating-links/not-a-token").status_code == 404
        login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": member["id"], "pin": "5678", "device_mode": "personal"},
        )
        assert login.status_code == 200
        assert login.json()["profile"]["pin_change_required"] is True
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        pin_change = client.post(
            "/api/v1/auth/pin",
            headers=member_headers,
            json={"current_pin": "5678", "new_pin": "6789"},
        )
        assert pin_change.status_code == 204
        assert client.get("/api/v1/auth/me").json()["profile"]["pin_change_required"] is False
        hidden_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert set(hidden_profile["profile"]) == {"id", "display_name"}
        assert hidden_profile["is_self"] is False
        assert hidden_profile["is_complete_history"] is False
        assert hidden_profile["rating_count"] == 0
        assert hidden_profile["ratings"] == []
        assert hidden_profile["averages"] == {}
        assert client.get("/api/v1/profiles/99999/ratings").status_code == 404
        updated_grinder = client.put(
            f"/api/v1/grinders/{grinder['id']}",
            headers=member_headers,
            json={
                "manufacturer": grinder["manufacturer"],
                "model": grinder["model"],
                "setting_unit": grinder["setting_unit"],
                "setting_step": grinder["setting_step"],
                "soft_min": grinder["soft_min"],
                "soft_max": grinder["soft_max"],
                "guidance": "Member-corrected guidance",
            },
        )
        assert updated_grinder.status_code == 422
        assert updated_grinder.json()["detail"] == "Predefined grinder details cannot be edited"
        assert (
            client.post(
                f"/api/v1/grinders/{grinder['id']}/archive", headers=member_headers
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/brews/{brew['id']}/void",
                headers=member_headers,
                json={"revision": finalized["revision"]},
            ).status_code
            == 403
        )

        hidden = client.get(f"/api/v1/brews/{brew['id']}/ratings").json()
        assert hidden == {
            "can_view": False,
            "own_rating": None,
            "ratings": [],
            "count": 0,
            "averages": {},
            "flavor_counts": {},
            "flavor_axes": [],
        }
        too_many_tags = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 8,
                "acidity": 3,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [
                    item["id"] for item in client.get("/api/v1/flavor-tags").json()[:6]
                ],
            },
        )
        assert too_many_tags.status_code == 422
        rated = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 8,
                "acidity": 3,
                "bitterness": 1,
                "sweetness": 4,
                "body": 3,
                "flavor_tag_ids": [fruity["id"]],
            },
        )
        assert rated.status_code == 200, rated.text
        assert rated.json()["can_view"] is True
        assert rated.json()["averages"]["liking"] == 7.5
        updated = client.post(
            f"/api/v1/brews/{brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 9,
                "acidity": 2,
                "bitterness": 1,
                "sweetness": 5,
                "body": 3,
                "flavor_tag_ids": [],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["count"] == 2
        assert updated.json()["averages"]["liking"] == 8

        own_profile = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert own_profile["is_self"] is True
        assert own_profile["is_complete_history"] is True
        assert own_profile["averages"] == {
            "liking": 9,
            "acidity": 2,
            "bitterness": 1,
            "sweetness": 5,
            "body": 3,
        }
        assert own_profile["favorite_coffees"] == [
            {
                "coffee_id": coffee["id"],
                "coffee_name": "Collider Blend",
                "coffee_roaster": "PSI Roasters",
                "rating_count": 1,
                "average_liking": 9,
            }
        ]
        comparison = own_profile["ratings"][0]
        assert comparison["total_rating_count"] == 2
        assert comparison["peer_count"] == 1
        assert comparison["peer_averages"] == {
            "liking": 7,
            "acidity": 4,
            "bitterness": 2,
            "sweetness": 3,
            "body": 4,
        }
        assert comparison["peer_deltas"] == {
            "liking": 2,
            "acidity": -2,
            "bitterness": -1,
            "sweetness": 2,
            "body": -1,
        }
        assert comparison["peer_flavor_counts"] == {"Fruity": 1}

        shared_admin_profile = client.get("/api/v1/profiles/1/ratings").json()
        assert shared_admin_profile["rating_count"] == 1
        assert shared_admin_profile["ratings"][0]["rating"]["liking"] == 7
        assert shared_admin_profile["ratings"][0]["peer_deltas"]["liking"] == -2

        scoped_comparisons = client.get(
            f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}"
        ).json()
        assert [item["brew_id"] for item in scoped_comparisons] == [brew["id"]]
        assert scoped_comparisons[0]["peer_averages"]["liking"] == 7
        assert client.get("/api/v1/ratings/me/comparisons").status_code == 422
        duplicate_ids = client.get(
            f"/api/v1/ratings/me/comparisons?brew_id={brew['id']}&brew_id={brew['id']}"
        )
        assert duplicate_ids.status_code == 422
        too_many_ids = "&".join(f"brew_id={item}" for item in range(1, 52))
        assert client.get(f"/api/v1/ratings/me/comparisons?{too_many_ids}").status_code == 422

        second_coffee = client.post(
            "/api/v1/coffees",
            headers=member_headers,
            json={"roaster": "Quiet Roasters", "name": "Solo Lot"},
        ).json()
        second_brew = client.post(
            "/api/v1/brews",
            headers=member_headers,
            json={
                "coffee_id": second_coffee["id"],
                "grinder_id": grinder["id"],
                "dripper_id": dripper["id"],
                "filter_id": brew_filter["id"],
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 92,
                "grinder_setting": 29,
            },
        ).json()
        client.post(
            f"/api/v1/brews/{second_brew['id']}/finalize",
            headers=member_headers,
            json={"total_brew_time_s": 190, "revision": second_brew["revision"]},
        )
        second_rating = client.post(
            f"/api/v1/brews/{second_brew['id']}/ratings",
            headers=member_headers,
            json={
                "liking": 6,
                "acidity": 1,
                "bitterness": 4,
                "sweetness": 2,
                "body": 5,
                "flavor_tag_ids": [],
            },
        )
        assert second_rating.status_code == 200

        comparison_ids = (second_brew["id"], brew["id"])
        comparison_query = "&".join(f"brew_id={item}" for item in comparison_ids)
        comparisons = client.get(f"/api/v1/ratings/me/comparisons?{comparison_query}").json()
        assert [item["brew_id"] for item in comparisons] == list(comparison_ids)
        assert comparisons[0]["peer_count"] == 0
        assert comparisons[0]["peer_averages"] == {}
        assert comparisons[0]["peer_deltas"] == {}
        assert comparisons[1]["peer_count"] == 1

        first_page = client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=1&offset=0").json()
        assert first_page["rating_count"] == 2
        assert first_page["next_offset"] == 1
        assert [item["brew"]["id"] for item in first_page["ratings"]] == [second_brew["id"]]
        assert first_page["averages"] == {
            "liking": 7.5,
            "acidity": 1.5,
            "bitterness": 2.5,
            "sweetness": 3.5,
            "body": 4,
        }
        assert [item["coffee_name"] for item in first_page["favorite_coffees"]] == [
            "Collider Blend",
            "Solo Lot",
        ]
        second_page = client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=1&offset=1").json()
        assert second_page["rating_count"] == 2
        assert second_page["next_offset"] is None
        assert [item["brew"]["id"] for item in second_page["ratings"]] == [brew["id"]]
        assert second_page["averages"] == first_page["averages"]
        assert second_page["favorite_coffees"] == first_page["favorite_coffees"]
        assert client.get(f"/api/v1/profiles/{member['id']}/ratings?limit=101").status_code == 422
        assert client.get(f"/api/v1/profiles/{member['id']}/ratings?offset=-1").status_code == 422

        client.post("/api/v1/auth/logout", headers=member_headers)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"profile_id": 1, "pin": "1234", "device_mode": "personal"},
        ).json()
        admin_headers = {"X-CSRF-Token": admin_login["csrf_token"]}
        complete_member_profile = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert complete_member_profile["rating_count"] == 2
        assert (
            client.post(
                f"/api/v1/brews/{second_brew['id']}/void",
                headers=admin_headers,
                json={
                    "revision": client.get(f"/api/v1/brews/{second_brew['id']}").json()["revision"]
                },
            ).status_code
            == 200
        )
        profile_after_void = client.get(f"/api/v1/profiles/{member['id']}/ratings").json()
        assert profile_after_void["rating_count"] == 1
        assert [item["brew"]["id"] for item in profile_after_void["ratings"]] == [brew["id"]]
        corrected = client.put(
            f"/api/v1/brews/{brew['id']}/correction",
            headers=admin_headers,
            json={
                "revision": client.get(f"/api/v1/brews/{brew['id']}").json()["revision"],
                "coffee_id": coffee["id"],
                "grinder_id": grinder["id"],
                "dripper_id": dripper["id"],
                "filter_id": brew_filter["id"],
                "source_preset_id": None,
                "dose_g": 15,
                "water_g": 240,
                "temperature_c": 93,
                "grinder_setting": 31,
                "servings": 2,
                "target_flow_g_s": 4.5,
                "bloom_water_g": 45,
                "bloom_time_s": 30,
                "pour_count": 3,
                "technique_note": None,
                "total_brew_time_s": 181,
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["temperature_c"] == 93
        voided = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers=admin_headers,
            json={"revision": corrected.json()["revision"]},
        )
        assert voided.status_code == 200
        repeat_void = client.post(
            f"/api/v1/brews/{brew['id']}/void",
            headers=admin_headers,
            json={"revision": voided.json()["revision"]},
        )
        assert repeat_void.status_code == 409
        assert repeat_void.json()["detail"] == "Only completed brews can be voided"
        inactive = client.get(f"/api/v1/rating-links/{finalized['rating_token']}").json()
        assert inactive == {"active": False, "brew": None}
