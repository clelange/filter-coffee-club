# Filter Coffee Club

A small, touch-first pour-over tracker for the High-Energy Physics coffee breaks at PSI. It runs as one FastAPI container, stores its state in SQLite, and serves a compiled Svelte 5 single-page interface with no runtime CDN dependencies.

## What is included

- First-run administrator setup; Argon2-hashed four-digit PINs; self-service PIN changes; CSRF-protected, server-side sessions.
- Temporary PINs for new accounts, enforced replacement on first sign-in, and administrator-controlled PIN-change requirements.
- Kiosk sign-in for the shared Raspberry Pi and personal sessions that expire exactly 84 hours after login.
- Coffee bag/lot catalog, extensible grinders/drippers/filters, editable FCC starting presets, and reference-sheet serving calculators.
- Draft recipe, high-contrast brew mode with Screen Wake Lock when available, final scale values, permanent QR invitation, and on-device rating handoff.
- A compact 1–9 liking scale, 0–5 sensory intensities, structured flavor tags, visibility rules, and lightweight SVG analytics.
- JSON/CSV exports, configurable branding, health endpoints, Alembic migrations, WAL mode, and structured request logs.

The bundled collider-ring/coffee-drop mark is original. The official PSI logo is deliberately not included.

## Deploy with Docker

```sh
cp .env.example .env
# Set FCC_PUBLIC_BASE_URL to the URL that phones can reach and pin
# FCC_IMAGE_TAG to a published release such as v2026.07.0.
docker compose pull
docker compose up -d --no-build
```

Open `http://localhost:8000` and create the first administrator. There are no default credentials and no public registration. The container runs one Uvicorn worker and expects one replica; SQLite is not suitable for horizontal application scaling.

Images are published for `linux/amd64` and `linux/arm64`, so the same release can run on a conventional server or a 64-bit Raspberry Pi. Production deployments should pin `FCC_IMAGE_TAG` to an exact release; `latest` is provided as a convenience and moves whenever a stable release is published.

### Raspberry Pi kiosk display

Complete the first-run administrator setup from a phone or computer, then launch the Pi browser at
the public application URL with `?kiosk=1`. For example:

```sh
chromium --kiosk 'https://coffee.example.psi.ch/?kiosk=1'
```

The browser remembers kiosk mode across navigation, reloads, sign-outs, and expired sessions. Kiosk
mode uses button-based PIN and number entry and keeps coffee, equipment, and administration text
editing on personal devices. Configure the startup URL with `?kiosk=1` so the preference is restored
if Chromium storage is cleared. To turn that browser back into a personal client, open the same URL
once with `?kiosk=0`.

To build the current checkout locally instead of pulling a release, use:

```sh
docker compose up --build
```

Traefik, TLS, VM provisioning, and scheduled host backups are intentionally outside this repository. When Traefik terminates HTTPS, set `FCC_COOKIE_SECURE=true`. Mounting `/data` persists the database and uploaded branding.

### Login throttling

Four-digit PIN logins use persistent per-profile throttling. After two incorrect attempts, the app
starts at a 30-second wait and doubles the delay after each further failure up to 15 minutes. A
successful login, PIN change/reset, profile reactivation, or 24 hours without a failure resets the
sequence. Existing authenticated sessions are not revoked when someone triggers a login delay.

For an internet-facing deployment, add source-based rate limiting at the trusted reverse proxy as
defense in depth. A reasonable starting point for the login endpoint is 30 requests per minute per
source with a burst of 10. The application deliberately does not use forwarded IP addresses as its
throttling identity because proxy topology, shared networks, and IP rotation make IP-only blocking
unreliable.

## Public demo mode

Set `FCC_DEMO_MODE=true` only for a disposable public demonstration. On an empty database, demo
mode creates four fictional profiles, four coffees, shared equipment, twelve completed brews, and
sample ratings. Every seeded profile uses PIN `1234`; **Demo Admin** can open the administration
area.

Demo mode also disables first-run administrator takeover, keeps branding under deployment control,
protects all records present at startup and the seeded PIN, rate-limits mutations, and caps the
number of records visitors can create. Visitors can create and edit their own new records. The
interface identifies the site as a public demo and asks visitors not to enter personal or
confidential information.

The included `render.yaml` creates a free Docker web service backed by ephemeral SQLite storage.
Render discards that storage whenever the free service sleeps, restarts, or redeploys, so the sample
dataset is rebuilt on the next start. After creating the service, copy its deploy hook URL into a
GitHub Actions repository secret named `RENDER_DEPLOY_HOOK_URL`. The `Reset demo` workflow triggers
a fresh deployment daily at 03:17 UTC and can also be run manually. Until that secret exists, the
scheduled workflow exits successfully without resetting anything.

## Upgrade and rollback

Back up the SQLite database before every upgrade. Then change `FCC_IMAGE_TAG` in `.env` and replace the container:

```sh
docker compose pull
docker compose up -d --no-build
```

Release tags make the container itself easy to roll back, but an older application may not understand a schema changed by a newer Alembic migration. Read the release's upgrade notes before downgrading and restore the matching database backup when a release includes incompatible schema changes.

## Releases

Stable releases use calendar versions in the form `vYYYY.MM.N`: the first release in July 2026 is `v2026.07.0`, followed by `v2026.07.1`. The final number resets to zero when the month changes. Release tags must never be moved or reused and are also used as container tags.

Maintainers publish a release from GitHub Actions by opening the **Release** workflow, choosing **Run workflow** on `main`, and entering the next version and any release-specific upgrade notes. The workflow reruns CI, publishes `linux/amd64` and `linux/arm64` images to `ghcr.io/clelange/filter-coffee-club`, attaches provenance and an SBOM, and then creates the matching GitHub release. It also updates the moving `latest` tag and adds an immutable `sha-<commit>` image tag.

GitHub Container Registry creates a new package as private. After the first successful release, a package owner must open the package settings and change its visibility to **Public** once; public GHCR images can then be pulled by deployments without registry credentials.

GitHub generates the changelog from merged pull requests. Use the `breaking-change`, `enhancement`, `bug`, `deployment`, or `dependencies` labels to categorize entries; use `skip-changelog` only for changes that should not appear in release notes. Pull request titles use Conventional Commits syntax, such as `feat: add brew comparison` or `fix(ratings): preserve the active session`, and should describe the user-visible change.

## Configuration

All environment variables use the `FCC_` prefix. Important values are:

| Variable              | Default                           | Purpose                                                                      |
| --------------------- | --------------------------------- | ---------------------------------------------------------------------------- |
| `FCC_PUBLIC_BASE_URL` | `http://filter-coffee-club.local` | Absolute URL encoded into QR links. Can also be changed in Admin → Branding. |
| `FCC_COOKIE_SECURE`   | `false`                           | Send the session cookie only over HTTPS.                                     |
| `FCC_ALLOWED_ORIGINS` | empty                             | Optional comma-separated additional trusted origins.                         |
| `FCC_DATA_DIR`        | `data` locally, `/data` in Docker | SQLite and uploaded-logo storage.                                            |
| `FCC_DATABASE_URL`    | derived SQLite URL                | Override only for local/testing scenarios.                                   |
| `FCC_LOG_LEVEL`       | `info`                            | Application and structured request log level.                                |
| `FCC_DEMO_MODE`       | `false`                           | Seed fictional data and enable public-demo protections.                      |

If the public URL is blank, the API uses the current request origin. Administrators see a warning while the development placeholder is active.

Docker Compose also reads `FCC_IMAGE` and `FCC_IMAGE_TAG` from `.env` to select the published container. These values configure Compose itself and are not passed into the application container.

## Local development

Python 3.11+, Node 22, [uv](https://docs.astral.sh/uv/), and pnpm are expected.

```sh
uv sync
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
uv run alembic upgrade head
uv run uvicorn app.main:app --app-dir backend --reload
```

SvelteKit's development server can be run separately with `pnpm --dir frontend dev`; API calls are same-origin in production, so the normal integrated check uses the static build served by FastAPI.

Regenerate the checked-in TypeScript API declaration after changing FastAPI schemas:

```sh
make types
```

## Tests and quality checks

Install the project dependencies and Git hooks once per checkout:

```sh
make install
make hooks
```

`make hooks` installs Chromium for Playwright and configures `prek` to format-check Python and frontend sources, lint GitHub Actions, validate lockfiles and common repository hazards, validate Conventional Commit messages, and run the complete non-Docker verification suite before pushes. Commit messages use `type(scope): subject`; the scope is optional, and `!` marks a breaking change. For example:

```text
feat: add brew comparison
fix(ratings): preserve the active session
feat(api)!: remove the legacy export shape
```

Apply the project formatters, run individual checks, or run the same suite used by the pre-push hook:

```sh
make format
make check
make test
make types-check
make e2e
make verify
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
