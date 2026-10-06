from dataclasses import dataclass


@dataclass(frozen=True)
class BrewActor:
    profile_id: int
    is_admin: bool = False


@dataclass(frozen=True)
class BrewNotifications:
    public_base_url: str
    demo_mode: bool = False
