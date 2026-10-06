from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class MattermostChannelOption(BaseModel):
    team_id: str
    team_name: str
    team_display_name: str
    channel_id: str
    channel_name: str
    channel_display_name: str


class MattermostVerifyInput(BaseModel):
    server_url: str = Field(default="https://mattermost.web.cern.ch", max_length=500)
    credential: SecretStr | None = None


class MattermostVerifyResponse(BaseModel):
    user_id: str
    username: str
    channels: list[MattermostChannelOption]


class MattermostSettingsUpdate(BaseModel):
    enabled: bool = False
    server_url: str = Field(default="https://mattermost.web.cern.ch", max_length=500)
    auth_mode: Literal["pat", "webhook"]
    credential: SecretStr | None = None
    team_id: str | None = Field(default=None, max_length=64)
    team_name: str | None = Field(default=None, max_length=160)
    channel_id: str | None = Field(default=None, max_length=64)
    channel_name: str | None = Field(default=None, max_length=160)
    channel_display_name: str | None = Field(default=None, max_length=160)
    announce_brew_started: bool = False
    mention_channel_on_started: bool = False
    announce_ready_to_rate: bool = False
    mention_channel_on_ready: bool = False

    @model_validator(mode="after")
    def validate_dependent_options(self) -> MattermostSettingsUpdate:
        if self.mention_channel_on_started and not self.announce_brew_started:
            raise ValueError("Started-brew mentions require started-brew announcements")
        if self.mention_channel_on_ready and not self.announce_ready_to_rate:
            raise ValueError("Ready-to-rate mentions require ready-to-rate announcements")
        if self.auth_mode == "pat" and self.enabled and not self.channel_id:
            raise ValueError("A Mattermost channel is required when PAT delivery is enabled")
        return self


class MattermostSettingsResponse(BaseModel):
    enabled: bool
    server_url: str
    auth_mode: Literal["pat", "webhook"]
    credential_configured: bool
    encryption_available: bool
    credential_status: Literal["not_configured", "ready", "key_unavailable", "unreadable"]
    account_user_id: str | None
    account_username: str | None
    team_id: str | None
    team_name: str | None
    channel_id: str | None
    channel_name: str | None
    channel_display_name: str | None
    announce_brew_started: bool
    mention_channel_on_started: bool
    announce_ready_to_rate: bool
    mention_channel_on_ready: bool
    last_tested_at: datetime | None
    last_delivery_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    pending_count: int = 0
    failed_count: int = 0


class MattermostTestResponse(BaseModel):
    delivered: bool
    message: str


class MattermostRetryResponse(BaseModel):
    requeued: int
