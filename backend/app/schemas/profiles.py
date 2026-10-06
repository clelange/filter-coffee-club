from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ._base import ORMModel


class ProfileIdentity(ORMModel):
    id: int
    display_name: str


class ProfilePublic(ORMModel):
    id: int
    display_name: str
    role: str
    active: bool
    pin_change_required: bool


class ProfileDirectoryItem(BaseModel):
    id: int
    display_name: str
    is_self: bool
    is_complete_history: bool
    rating_count: int


class BootstrapInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    pin: str
    device_mode: Literal["kiosk", "personal"] = "personal"

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class LoginInput(BaseModel):
    profile_id: int
    pin: str
    device_mode: Literal["kiosk", "personal"]

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class PinChange(BaseModel):
    current_pin: str
    new_pin: str

    @field_validator("current_pin", "new_pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if len(value) != 4 or not value.isdigit():
            raise ValueError("PIN must contain exactly four digits")
        return value


class ProfileCreate(BootstrapInput):
    role: Literal["member", "admin"] = "member"


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Literal["member", "admin"] | None = None
    active: bool | None = None
    pin_change_required: bool | None = None
    pin: str | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_optional_display_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("pin")
    @classmethod
    def validate_optional_pin(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 4 or not value.isdigit()):
            raise ValueError("PIN must contain exactly four digits")
        return value


class SessionResponse(BaseModel):
    profile: ProfilePublic
    csrf_token: str
    device_mode: str
    expires_at: datetime
