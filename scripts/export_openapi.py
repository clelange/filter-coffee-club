from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI document.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    app = create_app(Settings(data_dir=Path("/tmp/fcc-openapi")))
    args.output.write_text(json.dumps(app.openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()
