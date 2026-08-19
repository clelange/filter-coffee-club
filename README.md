# Filter Coffee Club

A small, touch-first pour-over tracker for the High-Energy Physics coffee breaks at PSI. It runs as one FastAPI container, stores its state in SQLite, and serves a compiled Svelte 5 single-page interface with no runtime CDN dependencies.

## How this has been built

I've built this web app with the Codex/ChatGPT app using GPT-Sol 5.6 Extra High Effort for all steps on macOS,
outlining how I would initially have thought that this app could work.
The overall idea was to have a filter coffee brewing tracker for our coffee breaks such that we can compare different
kinds of coffees but in particular also how brewing a respective coffee differently would affect the results.
I deliberately left a few options open for discussion to also receive some advice from the LLM.
From a colleague, I had received a PDF with some coffee brewing instructions that I also added to my initial prompt.
I asked for the app to be created using FastAPI as backend and SvelteKit as frontend since I'm familiar with both
and have previously obtained good results with it.
One constraint was that this app should work on a shared (Raspberry Pi) touch screen so that the brewing process
can easily be followed by the person brewing the coffee.
Furthermore, the whole app should run in a container for easier deployment.
Also, all people drinking the coffee should be able to quickly vote on.

The initial planning took about half an hour. Then Codex worked for more than an hour and produced a first version
of the app, which I then tested.
After identifying and compiling a list of bugs that I found, I sent those to Codex, which took about another half
hour to get those bugs fixed.
I then asked in a new session to deploy the container to my PC where I was already running podman with systemd and
cloudflared, then linked this to a Cloudflare tunnel follow instructions from Codex.
After receiving some feedback from beta testers, I largely forwarded the feedback to Codex to fix the identified
issues.
Over the following days, we then tested the app "in production".
During that time, I also asked for more user feedback, which I then rephrased into more technical prompts to get
it implemented.
In the end, I was able to build most of the app while watching sports, cooking, and performing other tasks that I
could interrupt from time to time to check the progress of Codex.
To make sure that the code that's pushed to Github works, I've set up extensive pre-comit hooks and CI testing.
I also often asked Codex to review the changes it had implemented, which in a large number of cases actually
surfaced some implementation issues that I then got fixed.

AI-generated text below!

## What is included

- First-run administrator setup; Argon2-hashed four-digit PINs; self-service PIN changes; CSRF-protected, server-side sessions.
- Temporary PINs for new accounts, enforced replacement on first sign-in, and administrator-controlled PIN-change requirements.
- Kiosk sign-in for the shared Raspberry Pi and personal sessions that expire exactly 84 hours after login.
- Coffee bag/lot catalog with responsive photo framing, extensible grinders/drippers/filters, editable FCC starting presets, and reference-sheet serving calculators.
- Draft recipe, high-contrast brew mode with Screen Wake Lock when available, final scale values, permanent QR invitation, and on-device rating handoff.
- A compact 1–9 liking scale, 0–5 sensory intensities, structured flavor tags, visibility rules, member tasting profiles with favorite coffees and per-brew comparisons, and lightweight SVG analytics.
- JSON/CSV exports, configurable branding, health endpoints, Alembic migrations, WAL mode, and structured request logs.

The bundled Filter Coffee Club mark is original. The official PSI logo is deliberately not included.

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

Traefik, TLS, VM provisioning, and scheduled host backups are intentionally outside this repository. When Traefik terminates HTTPS, set `FCC_COOKIE_SECURE=true`. Mounting `/data` persists the database, uploaded branding, and catalog photos.

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
mode creates four fictional profiles, four photographed coffees, photographed examples from the
shared equipment, twelve completed brews, and sample ratings. Every seeded profile uses PIN `1234`;
**Demo Admin** can open the administration area.

Demo mode also disables first-run administrator takeover, keeps branding under deployment control,
protects all records present at startup and the seeded PIN, rate-limits mutations, caps the number
of records visitors can create, and disables photo uploads. Visitors can create and edit their own
new text records. The interface identifies the site as a public demo and asks visitors not to enter
personal or confidential information.

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

| Variable                      | Default                           | Purpose                                                                                                                                        |
| ----------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `FCC_PUBLIC_BASE_URL`         | `http://filter-coffee-club.local` | Absolute URL encoded into QR links. Can also be changed in Admin → Branding.                                                                   |
| `FCC_COOKIE_SECURE`           | `false`                           | Send the session cookie only over HTTPS.                                                                                                       |
| `FCC_ALLOWED_ORIGINS`         | empty                             | Optional comma-separated additional trusted origins.                                                                                           |
| `FCC_DATA_DIR`                | `data` locally, `/data` in Docker | SQLite, branding, and catalog-photo storage.                                                                                                   |
| `FCC_DATABASE_URL`            | derived SQLite URL                | Override only for local/testing scenarios.                                                                                                     |
| `FCC_MAX_LOGO_BYTES`          | `2097152` (2 MiB)                 | Maximum accepted regular or brew-in-progress logo upload.                                                                                      |
| `FCC_MAX_LOGO_PIXELS`         | `16000000`                        | Maximum decoded pixel count for uploaded branding logos.                                                                                       |
| `FCC_MAX_CATALOG_PHOTO_BYTES` | `12582912` (12 MiB)               | Maximum accepted coffee or equipment photo upload. JPEG, PNG, WebP, HEIC, and HEIF are normalized to WebP with a maximum dimension of 1600 px. |
| `FCC_LOG_LEVEL`               | `info`                            | Application and structured request log level.                                                                                                  |
| `FCC_DEMO_MODE`               | `false`                           | Seed fictional data and enable public-demo protections.                                                                                        |
| `FCC_MATTERMOST_SECRET_KEY`   | empty                             | URL-safe Fernet key used to encrypt saved Mattermost PATs or webhook URLs. Required only when the Mattermost integration is configured.        |

If the public URL is blank, the API uses the current request origin. Administrators see a warning while the development placeholder is active.

### Mattermost notifications

Administrators can configure one Mattermost destination from Admin → Settings. The server
defaults to `https://mattermost.web.cern.ch`, with an incoming webhook selected for new
configurations. Personal Access Token (PAT) delivery remains available for advanced use cases.
Generate the required deployment encryption key once and keep it stable:

```sh
podman exec filter-coffee-club python -c \
  'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

For Docker Compose, replace `podman exec filter-coffee-club` with
`docker compose exec filter-coffee-club`. During local development, the equivalent command is
`uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.

Set the result as `FCC_MATTERMOST_SECRET_KEY` before saving a credential. The encrypted credential
is stored in SQLite, but the encryption key must be managed separately from database backups.
Changing or losing the key makes the saved credential unreadable; enter the credential again after
restoring the original key or clearing the old credential.

For Docker Compose, put the generated value in `.env` and recreate the container so the new
environment reaches the application:

```dotenv
FCC_MATTERMOST_SECRET_KEY=<generated Fernet key>
```

```sh
docker compose up -d --no-build --force-recreate
```

For a rootless Podman Quadlet deployment, keep the key in a separate owner-only environment file
instead of embedding it in the `.container` file. Create the file and set its contents to the same
environment declaration:

```sh
install -d -m 700 ~/.config/filter-coffee-club
install -m 600 /dev/null ~/.config/filter-coffee-club/filter-coffee-club.env
```

```dotenv
FCC_MATTERMOST_SECRET_KEY=<generated Fernet key>
```

Reference its absolute path from the Quadlet's `[Container]` section; replace `USER` with the account
that owns the user service:

```ini
[Container]
EnvironmentFile=/home/USER/.config/filter-coffee-club/filter-coffee-club.env
```

Reload the user manager and restart the generated service:

```sh
systemctl --user daemon-reload
systemctl --user restart filter-coffee-club.service
```

The application can confirm that it loaded a valid key without printing the key itself:

```sh
podman exec filter-coffee-club python -c \
  'from app.config import Settings; from app.mattermost import encryption_available; print(encryption_available(Settings()))'
```

This should print `True`; after reloading Admin → Settings, the Mattermost controls are enabled.
Keep the environment file out of version control and include the key in a separate, access-controlled
secret backup so restored database credentials remain decryptable.

When the key is missing or invalid, Admin → Settings displays **Mattermost setup is locked** and
disables destination, credential, announcement, testing, and retry controls. Configure the key and
restart the application; changing browser state cannot unlock the integration. Removing an existing
credential remains available so an installation with a lost key can clear the unreadable value.

For webhook mode, create an incoming webhook in the intended Mattermost channel and paste its full
URL. Filter Coffee Club always uses that webhook's default channel. Webhook URLs are secrets and
must belong to the configured Mattermost server. A test message can be sent before announcements
are enabled.

For PAT mode, use a dedicated non-admin service account. A PAT has the permissions of its account,
does not expire automatically, and must be a member of private channels it posts to. CERN users
must ask the CERN Mattermost team to enable PAT creation for the selected user or service account.
The setup screen verifies the account and lists its joined public and private channels. See the
[CERN integration guidance](https://mattermost.docs.cern.ch/faq/#integrations) and the
[Mattermost PAT documentation](https://developers.mattermost.com/integrate/reference/personal-access-token/).

To rotate a PAT or webhook, paste the replacement credential in Admin → Settings, verify a PAT if
applicable, save, and send a test message. Re-enter the credential whenever the Mattermost server
changes. PAT rotation for the same server and channel preserves queued announcements; changing the
server, transport, channel, or webhook cancels queued work for the previous destination.
Claimed work is rechecked immediately before delivery, but an HTTP request already in progress
cannot be recalled after a brew is cancelled or the destination changes.

Brew operations never wait for Mattermost. Announcements are stored in a durable outbox and retried
for up to 24 hours after transient failures. Before retrying a PAT delivery, the worker reconciles
its stable pending-post ID against Mattermost channel history and defers rather than posting if that
history cannot be checked safely. Incoming webhooks remain at-least-once and can rarely duplicate a
post if Mattermost accepted it immediately before a network timeout. Failed deliveries and manual
retry controls appear in Admin → Settings. The public demo never sends Mattermost traffic.
Channel-wide mentions are disabled by default and also depend on the posting account's channel
permissions and each recipient's preferences.

Docker Compose also reads `FCC_IMAGE` and `FCC_IMAGE_TAG` from `.env` to select the published container. These values configure Compose itself and are not passed into the application container.

## Local development

Python 3.11+, Node 22, [uv](https://docs.astral.sh/uv/), pnpm, and Git LFS are expected. Git LFS stores the bundled demo WebP assets; `make install` fetches them for the current checkout.

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

`make hooks` installs Chromium for Playwright and configures `prek` to format-check Python and frontend sources, lint GitHub Actions, validate lockfiles and common repository hazards, validate Conventional Commit messages, upload referenced Git LFS objects, and run the complete non-Docker verification suite before pushes. Commit messages use `type(scope): subject`; the scope is optional, and `!` marks a breaking change. For example:

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

Catalog photos and uploaded branding live beside SQLite under `/data/uploads`. A recoverable
application backup must copy or snapshot the entire `/data` volume, preferably while the
application is stopped. If Mattermost is configured, the recovery set must also contain the
matching `FCC_MATTERMOST_SECRET_KEY`: the key intentionally lives outside `/data` and is required
to decrypt the credential stored in SQLite. Keep that secret backup encrypted or owner-readable
only, separate from broadly accessible database copies.

For a Quadlet deployment using the environment-file layout above, back up
`~/.config/filter-coffee-club/filter-coffee-club.env` alongside each matching `/data` snapshot or
SQLite backup. A scheduled backup can use timestamp-paired files with restrictive permissions:

```sh
install -d -m 700 /path/to/secure-backups/filter-coffee-club
install -m 600 ~/.config/filter-coffee-club/filter-coffee-club.env \
  /path/to/secure-backups/filter-coffee-club/fcc_YYYYMMDDTHHMMSSZ.env
```

The SQLite-only procedure below is still useful for a consistent database backup, but it does not
include uploaded files or the external Mattermost key.

For an online, consistent copy, use SQLite's backup command against the mounted database:

```sh
docker compose exec filter-coffee-club \
  sqlite3 /data/fcc.sqlite3 ".backup '/data/fcc-backup.sqlite3'"
docker compose cp filter-coffee-club:/data/fcc-backup.sqlite3 ./fcc-backup.sqlite3
```

The slim production image may not include the `sqlite3` command on every platform. In that case, stop the container before copying `/data/fcc.sqlite3`, or run a temporary SQLite container against the same volume. Do not copy only the main file while the application is actively writing in WAL mode.

To restore a database-only backup, stop the application and keep a copy of the current `/data`
directory. If the database contains a Mattermost credential, restore its timestamp-matched secret
environment file with mode `0600` before starting the application. Then replace
`/data/fcc.sqlite3`, remove stale `fcc.sqlite3-wal` and `fcc.sqlite3-shm` files if present, and start
the application. Restore `/data/uploads` from the matching full backup whenever catalog photos or
branding must be recovered. Confirm the Mattermost key health in Admin → Settings after recovery;
Alembic automatically upgrades an older restored schema at startup.

## Data boundaries

Exports include coffees, brews, and ratings. They intentionally omit uploaded photo files, PIN
hashes, live sessions, CSRF values, and opaque rating tokens. Version one is manual pour-over only:
it does not connect to the TIMEMORE scale, run an in-app timer, store second-by-second pours, or
support offline writes.
