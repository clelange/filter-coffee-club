from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event

import pytest
from app.coffee_colors import COFFEE_COLOR_PALETTE, contrast_ratio
from app.config import Settings
from app.db import Base, build_engine, build_session_factory
from app.models import AppSettings, Coffee, Profile
from app.schemas.coffees import CoffeeInput
from app.services import coffees
from app.services.coffee_errors import (
    CoffeeConflictError,
    CoffeeNotFoundError,
    CoffeePermissionError,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def coffee_db(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'coffees.sqlite3'}")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    try:
        with build_session_factory(engine)() as db:
            db.add_all(
                [
                    Profile(id=1, display_name="Owner", pin_hash="unused"),
                    Profile(id=2, display_name="Other member", pin_hash="unused"),
                    AppSettings(id=1),
                ]
            )
            db.commit()
            yield db
    finally:
        engine.dispose()


def test_coffee_lifecycle_and_cloning_run_without_http(coffee_db: Session) -> None:
    payload = CoffeeInput(
        roaster="Orbit",
        name="Bombe",
        country="Ethiopia",
        region="Sidama",
        producer="Smallholders",
        purchase_location="  MAME, Zurich  ",
        process="Washed",
        roast_level="Light",
        roast_date=date(2026, 1, 10),
        opened_date=date(2026, 1, 20),
        variety="Heirloom",
        package_notes="Peach and tea",
    )
    coffee = coffees.create_coffee(coffee_db, payload, 1)
    assert coffee.available
    assert coffee.created_by_id == 1
    assert coffee.purchase_location == "MAME, Zurich"

    coffee.photo_path = "/uploads/catalog/source.webp"
    coffee.photo_focus_x, coffee.photo_focus_y, coffee.photo_zoom = 0.4, 0.6, 2
    coffee_db.commit()

    finished = coffees.finish_coffee(coffee_db, coffee.id)
    finished_at = finished.finished_at
    assert finished_at is not None and finished_at.tzinfo is not None
    assert not finished.available
    assert coffees.finish_coffee(coffee_db, coffee.id).finished_at == finished_at
    assert coffees.restore_coffee(coffee_db, coffee.id).available
    assert coffees.restore_coffee(coffee_db, coffee.id).finished_at is None
    coffees.finish_coffee(coffee_db, coffee.id)
    assert coffees.archive_coffee(coffee_db, coffee.id, is_admin=True).archived

    clone = coffees.clone_coffee(coffee_db, coffee.id, 2)
    for field in (
        "roaster",
        "name",
        "country",
        "region",
        "producer",
        "purchase_location",
        "process",
        "roast_level",
        "variety",
        "package_notes",
    ):
        assert getattr(clone, field) == getattr(coffee, field)
    assert clone.cloned_from_id == coffee.id
    assert clone.created_by_id == 2
    assert clone.chart_color != coffee.chart_color
    assert clone.available and not clone.archived
    assert clone.finished_at is None
    assert clone.roast_date is None and clone.opened_date is None
    assert clone.photo_path is None and clone.photo_framing is None
    assert clone.creation_token is None and clone.creation_request_hash is None


@pytest.mark.parametrize(
    ("color_fields", "expected"),
    [({}, "#ABCDEF"), ({"chart_color": None}, "#D55E00"), ({"chart_color": "#0072b2"}, "#0072B2")],
)
def test_update_distinguishes_omitted_automatic_and_explicit_colors(
    coffee_db: Session, color_fields: dict[str, str | None], expected: str
) -> None:
    first = coffees.create_coffee(
        coffee_db, CoffeeInput(roaster="Orbit", name="First", chart_color="#ABCDEF"), 1
    )
    occupied = coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Second"), 1)
    assert occupied.chart_color == "#0072B2"
    updated = coffees.update_coffee(
        coffee_db, first.id, CoffeeInput(roaster="Orbit", name="Updated", **color_fields)
    )
    assert updated.chart_color == expected
    assert updated.name == "Updated" and updated.created_by_id == 1
    assert occupied.chart_color == "#0072B2"


def test_idempotency_preserves_original_request_and_skips_creation_policy(
    coffee_db: Session,
) -> None:
    payload = CoffeeInput(roaster="Orbit", name="Original", roast_date=date(2026, 1, 10))
    key = "coffee-service-idempotency"
    created = coffees.create_coffee(coffee_db, payload, 1, idempotency_key=key)
    coffees.update_coffee(coffee_db, created.id, CoffeeInput(roaster="Orbit", name="Edited"))

    def reject_creation() -> None:
        raise AssertionError("Creation policy must not run for a replay")

    replay = coffees.create_coffee(
        coffee_db, payload, 1, idempotency_key=key, before_create=reject_creation
    )
    assert replay.id == created.id and replay.name == "Edited"
    for request, profile_id in [(CoffeeInput(roaster="Orbit", name="Edited"), 1), (payload, 2)]:
        with pytest.raises(CoffeeConflictError, match="Idempotency key was already used"):
            coffees.create_coffee(
                coffee_db,
                request,
                profile_id,
                idempotency_key=key,
                before_create=reject_creation,
            )
        assert not coffee_db.in_transaction()
    assert coffee_db.scalar(select(func.count(Coffee.id))) == 1


def test_idempotent_replay_returns_edits_committed_by_another_session(coffee_db: Session) -> None:
    payload = CoffeeInput(roaster="Orbit", name="Original")
    key = "coffee-service-replay-after-concurrent-edit"
    created = coffees.create_coffee(coffee_db, payload, 1, idempotency_key=key)
    factory = build_session_factory(coffee_db.get_bind())
    with factory() as other:
        coffees.update_coffee(other, created.id, CoffeeInput(roaster="Orbit", name="Edited"))
    replay = coffees.create_coffee(coffee_db, payload, 1, idempotency_key=key)
    assert replay.id == created.id and replay.name == "Edited"


@pytest.mark.parametrize("command", [coffees.finish_coffee, coffees.restore_coffee])
def test_lifecycle_rechecks_coffee_archived_by_another_session(
    coffee_db: Session, command: Callable[[Session, int], Coffee]
) -> None:
    coffee = coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Bag"), 1)
    coffees.finish_coffee(coffee_db, coffee.id)
    finished_at = coffee.finished_at
    factory = build_session_factory(coffee_db.get_bind())
    with factory() as other:
        coffees.archive_coffee(other, coffee.id, is_admin=True)
    with pytest.raises(CoffeeConflictError, match="Archived coffee cannot"):
        command(coffee_db, coffee.id)
    coffee_db.refresh(coffee)
    assert coffee.archived and coffee.finished_at == finished_at


def test_permissions_and_archived_lifecycle_raise_domain_errors(coffee_db: Session) -> None:
    coffee = coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Bag"), 1)
    with pytest.raises(CoffeePermissionError, match="Administrator access required"):
        coffees.archive_coffee(coffee_db, coffee.id, is_admin=False)
    assert not coffee_db.in_transaction()
    coffee_db.refresh(coffee)
    assert coffee.available and not coffee.archived

    coffees.archive_coffee(coffee_db, coffee.id, is_admin=True)
    for command in (coffees.finish_coffee, coffees.restore_coffee):
        with pytest.raises(CoffeeConflictError, match="Archived coffee cannot"):
            command(coffee_db, coffee.id)
        assert not coffee_db.in_transaction()
    coffee_db.refresh(coffee)
    assert coffee.archived and coffee.finished_at is None


def test_missing_coffee_raises_domain_error_and_leaves_session_usable(coffee_db: Session) -> None:
    with pytest.raises(CoffeeNotFoundError, match="Coffee not found"):
        coffees.update_coffee(coffee_db, 999, CoffeeInput(roaster="Orbit", name="Missing"))
    assert not coffee_db.in_transaction()
    assert coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Present"), 1).id


@pytest.mark.parametrize("idempotency_key", [None, "failed-coffee-service-creation"])
def test_failed_creation_rolls_back_settings_and_releases_color_reservation(
    coffee_db: Session, idempotency_key: str | None
) -> None:
    coffee_db.execute(delete(AppSettings))
    coffee_db.commit()
    payload = CoffeeInput(roaster="Orbit", name="Bag")
    with pytest.raises(IntegrityError):
        coffees.create_coffee(coffee_db, payload, 999, idempotency_key=idempotency_key)
    assert not coffee_db.in_transaction()
    assert coffee_db.get(AppSettings, 1) is None
    assert coffee_db.scalar(select(func.count(Coffee.id))) == 0
    created = coffees.create_coffee(coffee_db, payload, 1, idempotency_key=idempotency_key)
    assert created.chart_color == COFFEE_COLOR_PALETTE[0]
    assert coffee_db.get(AppSettings, 1) is not None


def test_failed_update_rolls_back_metadata_and_color_and_can_be_retried(
    coffee_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    coffee = coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Original"), 1)
    original_color = coffee.chart_color
    original_commit = coffee_db.commit

    def fail_after_flush() -> None:
        coffee_db.flush()
        raise RuntimeError("Storage failure")

    monkeypatch.setattr(coffee_db, "commit", fail_after_flush)
    with pytest.raises(RuntimeError, match="Storage failure"):
        coffees.update_coffee(
            coffee_db,
            coffee.id,
            CoffeeInput(roaster="Updated roaster", name="Updated", chart_color="#ABCDEF"),
        )
    assert not coffee_db.in_transaction()
    coffee_db.refresh(coffee)
    assert coffee.name == "Original" and coffee.roaster == "Orbit"
    assert coffee.chart_color == original_color
    monkeypatch.setattr(coffee_db, "commit", original_commit)
    assert (
        coffees.update_coffee(
            coffee_db, coffee.id, CoffeeInput(roaster="Orbit", name="Retried", chart_color=None)
        ).name
        == "Retried"
    )


@pytest.mark.parametrize("command", ["create", "clone"])
def test_rejected_creation_policy_rolls_back_and_precedes_clone_lookup(
    coffee_db: Session, command: str
) -> None:
    def reject_creation() -> None:
        coffee_db.add(Coffee(roaster="Policy", name="Uncommitted", created_by_id=1))
        coffee_db.flush()
        raise RuntimeError("Creation is disabled")

    with pytest.raises(RuntimeError, match="Creation is disabled"):
        if command == "create":
            coffees.create_coffee(
                coffee_db,
                CoffeeInput(roaster="Orbit", name="Bag"),
                1,
                before_create=reject_creation,
            )
        else:
            coffees.clone_coffee(coffee_db, 999, 1, before_create=reject_creation)
    assert not coffee_db.in_transaction()
    assert coffee_db.scalar(select(func.count(Coffee.id))) == 0


def test_automatic_color_uses_current_surface_instead_of_cached_settings(
    coffee_db: Session,
) -> None:
    cached_settings = coffee_db.get(AppSettings, 1)
    assert cached_settings is not None and cached_settings.color_surface == "#FFFDFC"
    factory = build_session_factory(coffee_db.get_bind())
    with factory() as other:
        other.execute(
            update(AppSettings).where(AppSettings.id == 1).values(color_surface="#0072B2")
        )
        other.commit()
    coffee = coffees.create_coffee(coffee_db, CoffeeInput(roaster="Orbit", name="Bag"), 1)
    assert contrast_ratio(coffee.chart_color, "#0072B2") >= 3
    assert cached_settings.color_surface == "#0072B2"


def test_color_reservation_is_held_until_the_coffee_write_commits(
    coffee_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    allocated = Event()
    second_entered = Event()
    second_finished = Event()
    release_first = Event()
    original_allocate = coffees._automatic_coffee_color
    factory = build_session_factory(coffee_db.get_bind())

    def pause_first_allocation(
        db: Session, coffee_id: int | None = None, excluded: tuple[str, ...] = ()
    ) -> str:
        if db.info["first"]:
            color = original_allocate(db, coffee_id, excluded)
            allocated.set()
            assert release_first.wait(timeout=10)
            return color
        second_entered.set()
        return original_allocate(db, coffee_id, excluded)

    monkeypatch.setattr(coffees, "_automatic_coffee_color", pause_first_allocation)

    def create(first: bool) -> str:
        with factory() as db:
            db.info["first"] = first
            coffee = coffees.create_coffee(db, CoffeeInput(roaster="Orbit", name=str(first)), 1)
            if not first:
                second_finished.set()
            return coffee.chart_color

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create, True)
        try:
            assert allocated.wait(timeout=10)
            second = executor.submit(create, False)
            assert second_entered.wait(timeout=10)
            assert not second_finished.wait(timeout=0.1)
        finally:
            release_first.set()
        first_color, second_color = first.result(timeout=10), second.result(timeout=10)
    assert first_color != second_color
    assert coffee_db.scalar(select(func.count(Coffee.id))) == 2
