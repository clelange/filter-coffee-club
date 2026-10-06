from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from app.config import Settings
from app.db import Base, build_engine, build_session_factory
from app.models import (
    AppSettings,
    Brew,
    Coffee,
    Grinder,
    MattermostIntegration,
    MattermostNotification,
    Profile,
)
from app.schemas import BrewCorrection, BrewCreate, BrewFinalize, BrewStatusChange, BrewUpdate
from app.services import brews
from app.services.brew_errors import (
    BrewConflictError,
    BrewPermissionError,
    BrewValidationError,
    UnusualBrewRatioError,
)
from app.services.brew_types import BrewActor, BrewNotifications
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


@dataclass
class BrewContext:
    db: Session
    owner: BrewActor
    collaborator: BrewActor
    outsider: BrewActor
    admin: BrewActor
    recipe: BrewCreate
    notifications: BrewNotifications


@pytest.fixture
def brew_context(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'brews.sqlite3'}")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    try:
        with build_session_factory(engine)() as db:
            owner = Profile(display_name="Owner", pin_hash="unused", role="member")
            collaborator = Profile(display_name="Collaborator", pin_hash="unused", role="member")
            outsider = Profile(display_name="Outsider", pin_hash="unused", role="member")
            admin = Profile(display_name="Admin", pin_hash="unused", role="admin")
            db.add_all([owner, collaborator, outsider, admin])
            db.flush()
            coffee = Coffee(roaster="Service tests", name="Sample coffee", created_by_id=owner.id)
            grinder = Grinder(
                definition_key="custom",
                manufacturer="Test",
                model="Hand grinder",
                setting_unit="clicks",
                setting_step=1,
            )
            db.add_all(
                [
                    coffee,
                    grinder,
                    AppSettings(id=1),
                    MattermostIntegration(
                        id=1,
                        enabled=True,
                        auth_mode="webhook",
                        credential_ciphertext="configured",
                        target_fingerprint="service-tests",
                        announce_brew_started=True,
                        announce_ready_to_rate=True,
                    ),
                ]
            )
            db.commit()
            yield BrewContext(
                db=db,
                owner=BrewActor(owner.id),
                collaborator=BrewActor(collaborator.id),
                outsider=BrewActor(outsider.id),
                admin=BrewActor(admin.id, is_admin=True),
                recipe=BrewCreate(
                    coffee_id=coffee.id,
                    grinder_id=grinder.id,
                    dose_g=15,
                    water_g=240,
                    temperature_c=94,
                    grinder_setting=20,
                ),
                notifications=BrewNotifications("https://coffee.invalid"),
            )
    finally:
        engine.dispose()


def active_count(db: Session) -> int:
    return db.scalar(select(AppSettings.active_brew_count))


def test_workflows_run_without_http_and_keep_notifications_atomic(
    brew_context: BrewContext,
) -> None:
    ctx = brew_context
    brew = brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications)
    assert isinstance(brew, Brew)
    assert active_count(ctx.db) == 1
    joined = brews.join_brew(ctx.db, brew.id, ctx.collaborator)
    updated = brews.update_brew(
        ctx.db,
        brew.id,
        BrewUpdate(**(ctx.recipe.model_dump() | {"water_g": 255}), revision=joined.revision),
        ctx.collaborator,
    )
    completed = brews.finalize_brew(
        ctx.db,
        brew.id,
        BrewFinalize(total_brew_time_s=180, revision=updated.revision),
        ctx.collaborator,
        ctx.notifications,
    )
    assert completed.status == "completed"
    assert completed.rating_token
    assert completed.water_g == 255
    assert active_count(ctx.db) == 0
    messages = list(
        ctx.db.scalars(select(MattermostNotification).order_by(MattermostNotification.id))
    )
    assert [item.event_type for item in messages] == ["brew_started", "ready_to_rate"]
    assert f"/rate/{completed.rating_token}" in messages[1].message

    corrected = brews.correct_completed_brew(
        ctx.db,
        brew.id,
        BrewCorrection(
            **ctx.recipe.model_dump(),
            revision=completed.revision,
            total_brew_time_s=190,
            operator_id=ctx.collaborator.profile_id,
        ),
        ctx.owner,
    )
    assert corrected.operator_id == ctx.collaborator.profile_id
    repeated = brews.clone_brew(ctx.db, brew.id, ctx.outsider, ctx.notifications)
    assert repeated.operator_id == ctx.outsider.profile_id
    assert [profile.id for profile in repeated.operators] == [ctx.outsider.profile_id]
    assert active_count(ctx.db) == 1
    cancelled = brews.cancel_brew(
        ctx.db,
        repeated.id,
        BrewStatusChange(revision=repeated.revision),
        ctx.outsider,
    )
    assert cancelled.status == "cancelled"
    assert active_count(ctx.db) == 0
    voided = brews.void_brew(
        ctx.db,
        brew.id,
        BrewStatusChange(revision=corrected.revision),
        ctx.admin,
    )
    assert voided.status == "voided"
    assert active_count(ctx.db) == 0
    assert set(ctx.db.scalars(select(MattermostNotification.state))) == {"cancelled"}


def test_outsider_cannot_finalize_a_brew(brew_context: BrewContext) -> None:
    ctx = brew_context
    brew = brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications)
    with pytest.raises(BrewPermissionError, match="Only a brew operator"):
        brews.finalize_brew(
            ctx.db,
            brew.id,
            BrewFinalize(total_brew_time_s=180, revision=brew.revision),
            ctx.outsider,
            ctx.notifications,
        )
    assert brews.load_brew(ctx.db, brew.id).status == "draft"
    assert active_count(ctx.db) == 1
    assert ctx.db.scalar(select(func.count(MattermostNotification.id))) == 1


def test_stale_finalization_rolls_back_coffee_completion(brew_context: BrewContext) -> None:
    ctx = brew_context
    brew = brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications)
    old_revision = brew.revision
    brews.join_brew(ctx.db, brew.id, ctx.collaborator)
    with pytest.raises(BrewConflictError, match="Brew changed"):
        brews.finalize_brew(
            ctx.db,
            brew.id,
            BrewFinalize(total_brew_time_s=180, revision=old_revision, mark_coffee_finished=True),
            ctx.owner,
            ctx.notifications,
        )
    stored = brews.load_brew(ctx.db, brew.id)
    assert stored.status == "draft"
    assert stored.revision == old_revision + 1
    assert stored.coffee.finished_at is None
    assert active_count(ctx.db) == 1


def test_notification_failure_rolls_back_entire_finalization(
    brew_context: BrewContext, monkeypatch
) -> None:
    ctx = brew_context
    brew = brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications)
    revision = brew.revision

    def fail_notification(*_args, **_kwargs) -> None:
        raise RuntimeError("Notification queue failed")

    monkeypatch.setattr(brews, "enqueue_brew_notification", fail_notification)
    with pytest.raises(RuntimeError, match="Notification queue failed"):
        brews.finalize_brew(
            ctx.db,
            brew.id,
            BrewFinalize(total_brew_time_s=180, revision=revision, mark_coffee_finished=True),
            ctx.owner,
            ctx.notifications,
        )
    stored = brews.load_brew(ctx.db, brew.id)
    assert stored.status == "draft"
    assert stored.revision == revision
    assert stored.rating_token is None
    assert stored.coffee.finished_at is None
    assert active_count(ctx.db) == 1
    assert ctx.db.scalar(select(func.count(MattermostNotification.id))) == 1


def test_failed_creation_does_not_commit_capacity_initialization(
    brew_context: BrewContext, monkeypatch
) -> None:
    ctx = brew_context
    ctx.db.execute(delete(AppSettings))
    ctx.db.commit()

    def fail_notification(*_args, **_kwargs) -> None:
        raise RuntimeError("Notification queue failed")

    monkeypatch.setattr(brews, "enqueue_brew_notification", fail_notification)
    with pytest.raises(RuntimeError, match="Notification queue failed"):
        brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications)
    assert ctx.db.scalar(select(AppSettings)) is None
    assert ctx.db.scalar(select(func.count(Brew.id))) == 0
    assert ctx.db.scalar(select(func.count(MattermostNotification.id))) == 0


def test_idempotent_replay_skips_new_creation_policy(brew_context: BrewContext) -> None:
    ctx = brew_context
    brew = brews.create_brew(
        ctx.db,
        ctx.recipe,
        ctx.owner,
        ctx.notifications,
        idempotency_key="service-retry-key",
    )
    brews.finalize_brew(
        ctx.db,
        brew.id,
        BrewFinalize(total_brew_time_s=180, revision=brew.revision),
        ctx.owner,
        ctx.notifications,
    )

    def reject_new_creation() -> None:
        raise AssertionError("A replay must not run creation policy")

    replay = brews.create_brew(
        ctx.db,
        ctx.recipe,
        ctx.owner,
        ctx.notifications,
        idempotency_key="service-retry-key",
        before_create=reject_new_creation,
    )
    assert replay.id == brew.id
    assert replay.status == "completed"
    assert active_count(ctx.db) == 0
    assert ctx.db.scalar(select(func.count(MattermostNotification.id))) == 2


@pytest.mark.parametrize("invalid_kind", ["fractional_clicks", "unusual_ratio"])
def test_validation_uses_domain_errors_and_releases_the_transaction(
    brew_context: BrewContext, invalid_kind: str
) -> None:
    ctx = brew_context
    overrides = (
        {"grinder_setting": 20.5} if invalid_kind == "fractional_clicks" else {"water_g": 100}
    )
    payload = BrewCreate(**(ctx.recipe.model_dump() | overrides))
    error = BrewValidationError if invalid_kind == "fractional_clicks" else UnusualBrewRatioError
    with pytest.raises(error):
        brews.create_brew(ctx.db, payload, ctx.owner, ctx.notifications)
    assert active_count(ctx.db) == 0
    assert ctx.db.scalar(select(func.count(Brew.id))) == 0
    assert ctx.db.scalar(select(func.count(MattermostNotification.id))) == 0
    assert brews.create_brew(ctx.db, ctx.recipe, ctx.owner, ctx.notifications).status == "draft"
