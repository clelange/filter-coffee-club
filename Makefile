.PHONY: install hooks format check test build e2e types types-check verify dev

install:
	uv sync
	pnpm --dir frontend install --frozen-lockfile

hooks:
	pnpm --dir frontend exec playwright install chromium
	uv run prek install --prepare-hooks

format:
	uv run ruff check --fix backend tests scripts migrations
	uv run ruff format backend tests scripts migrations
	pnpm --dir frontend format

check:
	uv run ruff check backend tests scripts migrations
	uv run ruff format --check backend tests scripts migrations
	pnpm --dir frontend format:check
	pnpm --dir frontend check

test:
	uv run pytest

build:
	pnpm --dir frontend build
	uv run python scripts/check_bundle.py

e2e: build
	pnpm --dir frontend exec playwright test

types:
	uv run python scripts/export_openapi.py openapi.json
	pnpm --dir frontend exec openapi-typescript ../openapi.json -o src/lib/generated-api.d.ts

types-check:
	uv run python scripts/check_generated_api.py

verify: check test types-check e2e

dev:
	uv run uvicorn app.main:app --app-dir backend --reload
