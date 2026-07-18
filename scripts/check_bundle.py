from __future__ import annotations

import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
asset_dir = ROOT / "frontend" / "build" / "_app" / "immutable"
budget = 150 * 1024
javascript = sorted(asset_dir.rglob("*.js"))
if not javascript:
    raise SystemExit("No built JavaScript found; run the frontend build first")

# This deliberately counts every route chunk, which is stricter than the initial-route budget.
compressed = sum(len(gzip.compress(path.read_bytes(), compresslevel=9)) for path in javascript)
print(f"All route JavaScript: {compressed / 1024:.1f} KiB gzip (budget {budget / 1024:.0f} KiB)")
if compressed > budget:
    raise SystemExit("Compressed JavaScript exceeds the bundle budget")
