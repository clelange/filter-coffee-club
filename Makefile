.PHONY: install check test build e2e types dev

install:
	uv sync
	corepack pnpm --dir frontend install --frozen-lockfile

check:
	uv run ruff check backend tests scripts migrations
	uv run ruff format --check backend tests scripts migrations
	corepack pnpm --dir frontend exec svelte-check --tsconfig ./tsconfig.json

test:
	uv run pytest

build:
	corepack pnpm --dir frontend build
	uv run python scripts/check_bundle.py

e2e: build
	corepack pnpm --dir frontend exec playwright test

types:
	uv run python scripts/export_openapi.py openapi.json
	corepack pnpm --dir frontend exec openapi-typescript ../openapi.json -o src/lib/generated-api.d.ts

dev:
	uv run uvicorn app.main:app --app-dir backend --reload
