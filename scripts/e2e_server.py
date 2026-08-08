from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    port = int(os.environ.get("E2E_PORT", "8000"))
    data_dir = Path(tempfile.mkdtemp(prefix="fcc-e2e-"))
    app = create_app(
        Settings(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'e2e.sqlite3'}",
            frontend_dir=ROOT / "frontend" / "build",
            public_base_url=f"http://127.0.0.1:{port}",
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
