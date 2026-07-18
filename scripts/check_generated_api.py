from __future__ import annotations

import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "frontend" / "src" / "lib" / "generated-api.d.ts"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="fcc-openapi-check-") as temp_dir:
        temp = Path(temp_dir)
        openapi = temp / "openapi.json"
        generated = temp / "generated-api.d.ts"

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "export_openapi.py"), str(openapi)],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                "pnpm",
                "--dir",
                "frontend",
                "exec",
                "openapi-typescript",
                str(openapi),
                "-o",
                str(generated),
            ],
            cwd=ROOT,
            check=True,
        )

        expected_text = EXPECTED.read_text()
        generated_text = generated.read_text()
        if expected_text == generated_text:
            print("Generated API declaration is up to date")
            return

        print("Generated API declaration is out of date; run `make types`", file=sys.stderr)
        sys.stderr.writelines(
            difflib.unified_diff(
                expected_text.splitlines(keepends=True),
                generated_text.splitlines(keepends=True),
                fromfile=str(EXPECTED.relative_to(ROOT)),
                tofile="freshly generated declaration",
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
