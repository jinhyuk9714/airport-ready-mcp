.PHONY: install dev test lint format run-api run-mcp smoke

install:
	uv sync --extra dev

dev:
	uv run uvicorn departure_ready.api.app:create_app --factory --reload

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

run-api:
	uv run departure-ready-api

run-mcp:
	uv run departure-ready-mcp

smoke:
	uv run python -m departure_ready.smoke
