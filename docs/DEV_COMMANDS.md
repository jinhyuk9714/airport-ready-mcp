# Dev commands

```bash
cp .env.example .env
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run departure-ready-api
uv run departure-ready-mcp
```

## Codex CLI examples

```bash
npm i -g @openai/codex
codex
```

Recommended for this repo:

```bash
codex --sandbox workspace-write --ask-for-approval on-request
```
