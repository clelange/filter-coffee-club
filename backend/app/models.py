from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .coffee_colors import COFFEE_COLOR_PALETTE
from .db import Base, UTCDateTime, utcnow

rating_flavor_tags = Table(
    "rating_flavor_tags",
    Base.metadata,
    Column("rating_id", ForeignKey("ratings.id", ondelete="CASCADE"), primary_key=True),
    Column("flavor_tag_id", ForeignKey("flavor_tags.id"), primary_key=True),
)

brew_operators = Table(
    "brew_operators",
    Base.metadata,
    Column("brew_id", ForeignKey("brews.id", ondelete="CASCADE"), primary_key=True),
    Column("profile_id", ForeignKey("profiles.id"), primary_key=True, index=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class PhotoFramingMixin:
    photo_focus_x: Mapped[float | None] = mapped_column(Float)
    photo_focus_y: Mapped[float | None] = mapped_column(Float)
    photo_zoom: Mapped[float | None] = mapped_column(Float)

    @property
    def photo_framing(self) -> dict[str, float] | None:
        if self.photo_focus_x is None or self.photo_focus_y is None or self.photo_zoom is None:
            return None
        return {
            "focus_x": self.photo_focus_x,
            "focus_y": self.photo_focus_y,
            "zoom": self.photo_zoom,
        }


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = (CheckConstraint("role IN ('member', 'admin')", name="ck_profile_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), unique=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    pin_change_required: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    login_blocked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())

    sessions: Mapped[list[LoginSession]] = relationship(back_populates="profile")


class LoginSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("device_mode IN ('kiosk', 'personal')", name="ck_session_device_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    device_mode: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    profile: Mapped[Profile] = relationship(back_populates="sessions")


class Coffee(PhotoFramingMixin, TimestampMixin, Base):
    __tablename__ = "coffees"

    id: Mapped[int] = mapped_column(primary_key=True)
    roaster: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(160))
    producer: Mapped[str | None] = mapped_column(String(160))
    purchase_location: Mapped[str | None] = mapped_column(String(160))
    process: Mapped[str | None] = mapped_column(String(100))
    roast_level: Mapped[str | None] = mapped_column(String(60))
    roast_date: Mapped[date | None] = mapped_column(Date)
    opened_date: Mapped[date | None] = mapped_column(Date)
    variety: Mapped[str | None] = mapped_column(String(160))
    package_notes: Mapped[str | None] = mapped_column(Text)
    chart_color: Mapped[str] = mapped_column(String(7), default=COFFEE_COLOR_PALETTE[0])
    photo_path: Mapped[str | None] = mapped_column(String(500))
    creation_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    creation_request_hash: Mapped[str | None] = mapped_column(String(64))
    cloned_from_id: Mapped[int | None] = mapped_column(ForeignKey("coffees.id"))
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))

    @property
    def available(self) -> bool:
        return not self.archived and self.finished_at is None


class Grinder(PhotoFramingMixin, TimestampMixin, Base):
    __tablename__ = "grinders"
    __table_args__ = (
        CheckConstraint("setting_step > 0", name="ck_grinder_setting_step_positive"),
        CheckConstraint(
            "soft_min IS NULL OR soft_max IS NULL OR soft_min <= soft_max",
            name="ck_grinder_soft_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_key: Mapped[str] = mapped_column(String(64), default="custom")
    manufacturer: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(120))
    setting_unit: Mapped[str] = mapped_column(String(40), default="clicks")
    setting_step: Mapped[float] = mapped_column(Float, default=1)
    soft_min: Mapped[float | None] = mapped_column(Float)
    soft_max: Mapped[float | None] = mapped_column(Float)
    guidance: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Dripper(PhotoFramingMixin, TimestampMixin, Base):
    __tablename__ = "drippers"

    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class BrewFilter(PhotoFramingMixin, TimestampMixin, Base):
    __tablename__ = "filters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class RecipePreset(TimestampMixin, Base):
    __tablename__ = "recipe_presets"
    __table_args__ = (
        CheckConstraint("ratio > 1 AND ratio <= 30", name="ck_preset_ratio"),
        CheckConstraint(
            "temperature_min_c <= temperature_max_c", name="ck_preset_temperature_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    ratio: Mapped[float] = mapped_column(Float)
    temperature_min_c: Mapped[float] = mapped_column(Float)
    temperature_max_c: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    reference_setting_min: Mapped[float | None] = mapped_column(Float)
    reference_setting_max: Mapped[float | None] = mapped_column(Float)

    grinder_ranges: Mapped[list[PresetGrinderRange]] = relationship(
        back_populates="preset", cascade="all, delete-orphan"
    )


class PresetGrinderRange(Base):
    __tablename__ = "preset_grinder_ranges"
    __table_args__ = (
        UniqueConstraint("preset_id", "grinder_id"),
        CheckConstraint("setting_min <= setting_max", name="ck_preset_grinder_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preset_id: Mapped[int] = mapped_column(ForeignKey("recipe_presets.id", ondelete="CASCADE"))
    grinder_id: Mapped[int] = mapped_column(ForeignKey("grinders.id"))
    setting_min: Mapped[float] = mapped_column(Float)
    setting_max: Mapped[float] = mapped_column(Float)

    preset: Mapped[RecipePreset] = relationship(back_populates="grinder_ranges")
    grinder: Mapped[Grinder] = relationship()


class Brew(TimestampMixin, Base):
    __tablename__ = "brews"
    __table_args__ = (
        CheckConstraint("dose_g > 0", name="ck_brew_dose_positive"),
        CheckConstraint("water_g > 0", name="ck_brew_water_positive"),
        CheckConstraint("target_ratio > 0", name="ck_brew_target_ratio_positive"),
        CheckConstraint("temperature_c BETWEEN 50 AND 100", name="ck_brew_temperature"),
        CheckConstraint("servings > 0", name="ck_brew_servings_positive"),
        CheckConstraint(
            "status IN ('draft', 'completed', 'cancelled', 'voided')",
            name="ck_brew_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coffee_id: Mapped[int] = mapped_column(ForeignKey("coffees.id"))
    operator_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    grinder_id: Mapped[int] = mapped_column(ForeignKey("grinders.id"))
    dripper_id: Mapped[int | None] = mapped_column(ForeignKey("drippers.id"))
    filter_id: Mapped[int | None] = mapped_column(ForeignKey("filters.id"))
    source_preset_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_presets.id"))
    cloned_from_id: Mapped[int | None] = mapped_column(ForeignKey("brews.id"))
    dose_g: Mapped[float] = mapped_column(Float)
    water_g: Mapped[float] = mapped_column(Float)
    target_ratio: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    grinder_setting: Mapped[float] = mapped_column(Float)
    servings: Mapped[int] = mapped_column(Integer, default=1)
    target_flow_g_s: Mapped[float | None] = mapped_column(Float)
    total_brew_time_s: Mapped[int | None] = mapped_column(Integer)
    bloom_water_g: Mapped[float | None] = mapped_column(Float)
    bloom_time_s: Mapped[int | None] = mapped_column(Integer)
    pour_count: Mapped[int | None] = mapped_column(Integer)
    technique_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    creation_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    creation_request_hash: Mapped[str | None] = mapped_column(String(64))
    rating_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    coffee: Mapped[Coffee] = relationship()
    operator: Mapped[Profile] = relationship()
    operators: Mapped[list[Profile]] = relationship(secondary=brew_operators)
    grinder: Mapped[Grinder] = relationship()
    dripper: Mapped[Dripper | None] = relationship()
    brew_filter: Mapped[BrewFilter | None] = relationship()
    source_preset: Mapped[RecipePreset | None] = relationship()
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="brew", cascade="all, delete-orphan"
    )


class FlavorTag(TimestampMixin, Base):
    __tablename__ = "flavor_tags"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("flavor_tags.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parent: Mapped[FlavorTag | None] = relationship(remote_side="FlavorTag.id")


class Rating(TimestampMixin, Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("brew_id", "profile_id"),
        CheckConstraint("liking BETWEEN 1 AND 9", name="ck_rating_liking"),
        CheckConstraint("acidity BETWEEN 0 AND 5", name="ck_rating_acidity"),
        CheckConstraint("bitterness BETWEEN 0 AND 5", name="ck_rating_bitterness"),
        CheckConstraint("sweetness BETWEEN 0 AND 5", name="ck_rating_sweetness"),
        CheckConstraint("body BETWEEN 0 AND 5", name="ck_rating_body"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brew_id: Mapped[int] = mapped_column(ForeignKey("brews.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    liking: Mapped[int] = mapped_column(Integer)
    acidity: Mapped[int] = mapped_column(Integer)
    bitterness: Mapped[int] = mapped_column(Integer)
    sweetness: Mapped[int] = mapped_column(Integer)
    body: Mapped[int] = mapped_column(Integer)

    brew: Mapped[Brew] = relationship(back_populates="ratings")
    profile: Mapped[Profile] = relationship()
    flavor_tags: Mapped[list[FlavorTag]] = relationship(secondary=rating_flavor_tags)


DEFAULT_BREWING_LOGO_PATH = "/brand/filter-coffee-club-brewing.svg"


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    app_name: Mapped[str] = mapped_column(String(120), default="Filter Coffee Club")
    subtitle: Mapped[str] = mapped_column(
        String(240), default="High-Energy Physics coffee breaks at PSI"
    )
    public_base_url: Mapped[str | None] = mapped_column(String(500))
    logo_path: Mapped[str | None] = mapped_column(String(500))
    brewing_logo_path: Mapped[str | None] = mapped_column(
        String(500), default=DEFAULT_BREWING_LOGO_PATH, server_default=DEFAULT_BREWING_LOGO_PATH
    )
    color_cream: Mapped[str] = mapped_column(String(7), default="#F6F1E8")
    color_surface: Mapped[str] = mapped_column(String(7), default="#FFFDFC")
    color_ink: Mapped[str] = mapped_column(String(7), default="#241C19")
    color_coffee: Mapped[str] = mapped_column(String(7), default="#6B3F2A")
    color_cyan: Mapped[str] = mapped_column(String(7), default="#007F9E")
    color_amber: Mapped[str] = mapped_column(String(7), default="#D88700")
    max_active_brews: Mapped[int] = mapped_column(Integer, default=2)
    active_brew_count: Mapped[int] = mapped_column(Integer, default=0)


class MattermostIntegration(TimestampMixin, Base):
    __tablename__ = "mattermost_integrations"
    __table_args__ = (
        CheckConstraint("auth_mode IN ('pat', 'webhook')", name="ck_mattermost_auth_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    server_url: Mapped[str] = mapped_column(String(500), default="https://mattermost.web.cern.ch")
    auth_mode: Mapped[str] = mapped_column(String(20), default="webhook")
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    account_user_id: Mapped[str | None] = mapped_column(String(64))
    account_username: Mapped[str | None] = mapped_column(String(120))
    team_id: Mapped[str | None] = mapped_column(String(64))
    team_name: Mapped[str | None] = mapped_column(String(160))
    channel_id: Mapped[str | None] = mapped_column(String(64))
    channel_name: Mapped[str | None] = mapped_column(String(160))
    channel_display_name: Mapped[str | None] = mapped_column(String(160))
    target_fingerprint: Mapped[str | None] = mapped_column(String(64))
    announce_brew_started: Mapped[bool] = mapped_column(Boolean, default=False)
    mention_channel_on_started: Mapped[bool] = mapped_column(Boolean, default=False)
    announce_ready_to_rate: Mapped[bool] = mapped_column(Boolean, default=False)
    mention_channel_on_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_delivery_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)


class MattermostNotification(TimestampMixin, Base):
    __tablename__ = "mattermost_notifications"
    __table_args__ = (
        UniqueConstraint("brew_id", "event_type", name="uq_mattermost_notification_event"),
        CheckConstraint(
            "event_type IN ('brew_started', 'ready_to_rate')",
            name="ck_mattermost_notification_event_type",
        ),
        CheckConstraint(
            "state IN ('pending', 'delivering', 'sent', 'failed', 'cancelled')",
            name="ck_mattermost_notification_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brew_id: Mapped[int] = mapped_column(ForeignKey("brews.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    target_fingerprint: Mapped[str] = mapped_column(String(64))
    pending_post_id: Mapped[str] = mapped_column(String(80), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    mattermost_post_id: Mapped[str | None] = mapped_column(String(64))

    brew: Mapped[Brew] = relationship()
