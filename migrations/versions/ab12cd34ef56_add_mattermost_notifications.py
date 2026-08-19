"""Add Mattermost integration settings and durable notification outbox."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab12cd34ef56"
down_revision: str | Sequence[str] | None = "f4a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mattermost_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "server_url",
            sa.String(length=500),
            nullable=False,
            server_default="https://mattermost.web.cern.ch",
        ),
        sa.Column("auth_mode", sa.String(length=20), nullable=False, server_default="webhook"),
        sa.Column("credential_ciphertext", sa.Text(), nullable=True),
        sa.Column("account_user_id", sa.String(length=64), nullable=True),
        sa.Column("account_username", sa.String(length=120), nullable=True),
        sa.Column("team_id", sa.String(length=64), nullable=True),
        sa.Column("team_name", sa.String(length=160), nullable=True),
        sa.Column("channel_id", sa.String(length=64), nullable=True),
        sa.Column("channel_name", sa.String(length=160), nullable=True),
        sa.Column("channel_display_name", sa.String(length=160), nullable=True),
        sa.Column("target_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("announce_brew_started", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "mention_channel_on_started", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "announce_ready_to_rate", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "mention_channel_on_ready", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_delivery_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("auth_mode IN ('pat', 'webhook')", name="ck_mattermost_auth_mode"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "mattermost_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brew_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("target_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("pending_post_id", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("mattermost_post_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('brew_started', 'ready_to_rate')",
            name="ck_mattermost_notification_event_type",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'delivering', 'sent', 'failed', 'cancelled')",
            name="ck_mattermost_notification_state",
        ),
        sa.ForeignKeyConstraint(["brew_id"], ["brews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brew_id", "event_type", name="uq_mattermost_notification_event"),
        sa.UniqueConstraint("pending_post_id"),
    )
    op.create_index("ix_mattermost_notifications_state", "mattermost_notifications", ["state"])
    op.create_index(
        "ix_mattermost_notifications_next_attempt_at",
        "mattermost_notifications",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mattermost_notifications_next_attempt_at", table_name="mattermost_notifications"
    )
    op.drop_index("ix_mattermost_notifications_state", table_name="mattermost_notifications")
    op.drop_table("mattermost_notifications")
    op.drop_table("mattermost_integrations")
