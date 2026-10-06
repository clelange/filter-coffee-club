from __future__ import annotations

import asyncio
import io
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.schemas import MattermostChannelOption, MattermostVerifyResponse
from fastapi.testclient import TestClient
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        frontend_dir=tmp_path / "missing-frontend",
        public_base_url="http://fcc.test",
        **overrides,
    )
    return TestClient(create_app(settings))


def build_demo_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'demo.sqlite3'}",
        frontend_dir=tmp_path / "missing-frontend",
        public_base_url="http://demo.fcc.test",
        demo_mode=True,
    )
    return TestClient(create_app(settings))


def bootstrap(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/auth/bootstrap", json={"display_name": "Ada", "pin": "1234"})
    assert response.status_code == 200, response.text
    session = response.json()
    return session, {"X-CSRF-Token": session["csrf_token"]}


def image_upload(format_name: str = "PNG", size: tuple[int, int] = (2000, 1000)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#8f4f38").save(output, format=format_name)
    return output.getvalue()


def multipicture_jpeg_upload() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2000, 1000), "#8f4f38").save(
        output,
        format="MPO",
        save_all=True,
        append_images=[Image.new("RGB", (320, 180), "#ffffff")],
    )
    return output.getvalue()


def animated_gif_upload() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (5, 5), "#8f4f38").save(
        output,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (5, 5), "#ffffff")],
        duration=100,
        loop=0,
    )
    return output.getvalue()


async def inactive_mattermost_worker(*_args: object) -> None:
    await asyncio.Event().wait()


def mattermost_verification() -> MattermostVerifyResponse:
    return MattermostVerifyResponse(
        user_id="mattermost-user-1",
        username="coffee-bot",
        channels=[
            MattermostChannelOption(
                team_id="team-1",
                team_name="coffee-team",
                team_display_name="Coffee Team",
                channel_id="channel-1",
                channel_name="coffee-breaks",
                channel_display_name="Coffee breaks",
            )
        ],
    )


def mattermost_settings_payload(**overrides: object) -> dict[str, object]:
    return {
        "enabled": True,
        "server_url": "https://mattermost.web.cern.ch",
        "auth_mode": "pat",
        "credential": "mattermost-secret-token",
        "team_id": "team-1",
        "team_name": "Coffee Team",
        "channel_id": "channel-1",
        "channel_name": "coffee-breaks",
        "channel_display_name": "Coffee breaks",
        "announce_brew_started": True,
        "mention_channel_on_started": True,
        "announce_ready_to_rate": True,
        "mention_channel_on_ready": False,
        **overrides,
    }


def mattermost_webhook_payload(**overrides: object) -> dict[str, object]:
    return {
        "enabled": True,
        "server_url": "https://mattermost.web.cern.ch",
        "auth_mode": "webhook",
        "credential": "https://mattermost.web.cern.ch/hooks/coffee-webhook/",
        "team_id": "ignored-team",
        "team_name": "Ignored Team",
        "channel_id": "ignored-channel",
        "channel_name": "ignored-channel",
        "channel_display_name": "Ignored channel",
        "announce_brew_started": True,
        "mention_channel_on_started": False,
        "announce_ready_to_rate": True,
        "mention_channel_on_ready": False,
        **overrides,
    }


def settings_payload(settings: dict, max_active_brews: int) -> dict:
    return {
        "app_name": settings["app_name"],
        "subtitle": settings["subtitle"],
        "public_base_url": settings["public_base_url"],
        "color_cream": settings["color_cream"],
        "color_surface": settings["color_surface"],
        "color_ink": settings["color_ink"],
        "color_coffee": settings["color_coffee"],
        "color_cyan": settings["color_cyan"],
        "color_amber": settings["color_amber"],
        "max_active_brews": max_active_brews,
    }
