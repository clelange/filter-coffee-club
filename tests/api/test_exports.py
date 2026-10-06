from __future__ import annotations

import io
import zipfile
from pathlib import Path

from tests.api_helpers import bootstrap, build_client


def test_export_omits_auth_secrets(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        _session, headers = bootstrap(client)
        response = client.get("/api/v1/exports/json")
        assert response.status_code == 200
        body = response.text
        assert "pin_hash" not in body
        assert "rating_token" not in body
        assert "failed_login_attempts" not in body
        assert "last_failed_login_at" not in body
        assert "login_blocked_until" not in body
        csv_response = client.get("/api/v1/exports/csv")
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(csv_response.content)) as archive:
            combined = "".join(archive.read(name).decode() for name in archive.namelist())
        assert "pin_hash" not in combined
        assert "rating_token" not in combined
