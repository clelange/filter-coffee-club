# Filter Coffee Club

A small, touch-first pour-over tracker for the High-Energy Physics coffee breaks at PSI. It runs as one FastAPI container, stores its state in SQLite, and serves a compiled Svelte 5 single-page interface with no runtime CDN dependencies.

## What is included

- First-run administrator setup; Argon2-hashed four-digit PINs; CSRF-protected, server-side sessions.
- Kiosk sign-in for the shared Raspberry Pi and personal sessions that expire exactly 84 hours after login.
- Coffee bag/lot catalog, extensible grinders/drippers/filters, editable FCC starting presets, and reference-sheet serving calculators.
- Draft recipe, high-contrast brew mode with Screen Wake Lock when available, final scale values, permanent QR invitation, and on-device rating handoff.
- A compact 1–9 liking scale, 0–5 sensory intensities, structured flavor tags, visibility rules, and lightweight SVG analytics.
- JSON/CSV exports, configurable branding, health endpoints, Alembic migrations, WAL mode, and structured request logs.

The bundled collider-ring/coffee-drop mark is original. The official PSI logo is deliberately not included.

## Run with Docker

```sh
cp .env.example .env
# Set FCC_PUBLIC_BASE_URL to the URL that phones can reach.
docker compose up --build
```

Open `http://localhost:8000` and create the first administrator. There are no default credentials and no public registration. The container runs one Uvicorn worker and expects one replica; SQLite is not suitable for horizontal application scaling.

Traefik, TLS, VM provisioning, and scheduled host backups are intentionally outside this repository. When Traefik terminates HTTPS, set `FCC_COOKIE_SECURE=true`. Mounting `/data` persists the database and uploaded branding.

## Configuration

All environment variables use the `FCC_` prefix. Important values are:

| Variable | Default | Purpose |
|---|---|---|
| `FCC_PUBLIC_BASE_URL` | `http://filter-coffee-club.local` | Absolute URL encoded into QR links. Can also be changed in Admin → Branding. |
| `FCC_COOKIE_SECURE` | `false` | Send the session cookie only over HTTPS. |
| `FCC_ALLOWED_ORIGINS` | empty | Optional comma-separated additional trusted origins. |
| `FCC_DATA_DIR` | `data` locally, `/data` in Docker | SQLite and uploaded-logo storage. |
| `FCC_DATABASE_URL` | derived SQLite URL | Override only for local/testing scenarios. |
| `FCC_LOG_LEVEL` | `info` | Application and structured request log level. |

If the public URL is blank, the API uses the current request origin. Administrators see a warning while the development placeholder is active.

## Local development

Python 3.11+, Node 22, [uv](https://docs.astral.sh/uv/), and pnpm are expected.

```sh
uv sync
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build
uv run alembic upgrade head
uv run uvicorn app.main:app --app-dir backend --reload
```

SvelteKit's development server can be run separately with `corepack pnpm --dir frontend dev`; API calls are same-origin in production, so the normal integrated check uses the static build served by FastAPI.

Regenerate the checked-in TypeScript API declaration after changing FastAPI schemas:

```sh
make types
```

## Tests and quality checks

```sh
make check
make test
corepack pnpm --dir frontend exec playwright install chromium
make e2e
```

The Playwright flow covers a 1024×600 Pi operator journey and a touch-enabled 393×851 phone rating opened through the same path as a QR scan. The production build is route-split and reports compressed JavaScript chunks far below the 150 KiB initial-route budget.

## Backup and restore

For an online, consistent copy, use SQLite's backup command against the mounted database:

```sh
docker compose exec filter-coffee-club \
  sqlite3 /data/fcc.sqlite3 ".backup '/data/fcc-backup.sqlite3'"
docker compose cp filter-coffee-club:/data/fcc-backup.sqlite3 ./fcc-backup.sqlite3
```

The slim production image may not include the `sqlite3` command on every platform. In that case, stop the container before copying `/data/fcc.sqlite3`, or run a temporary SQLite container against the same volume. Do not copy only the main file while the application is actively writing in WAL mode.

To restore, stop the application, keep a copy of the current `/data` directory, replace `/data/fcc.sqlite3` with the backup, remove stale `fcc.sqlite3-wal` and `fcc.sqlite3-shm` files if present, then start the application. Alembic automatically upgrades an older restored schema at startup.

## Data boundaries

Exports include coffees, brews, and ratings. They intentionally omit PIN hashes, live sessions, CSRF values, and opaque rating tokens. Version one is manual pour-over only: it does not connect to the TIMEMORE scale, run an in-app timer, store second-by-second pours, or support offline writes.
