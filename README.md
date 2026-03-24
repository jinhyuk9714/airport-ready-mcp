# Departure Ready MCP

출국 직전 질문을 공식 데이터로 정리해 주는 **공항 준비 MCP + HTTP API** 프로젝트입니다.

핵심 질문:
- 지금 공항 출발해도 돼?
- 차 끌고 가도 괜찮아?
- 이 물건 기내 반입 돼?
- 스마트패스 / 셀프백드랍 / 우대출구 대상이야?
- 터미널 안에서 약국 / ATM / 환전 / 라운지 어디야?

## Current scope
- strong support: `ICN`, `GMP`, `CJU`
- selected support: `PUS`, `CJJ`, `TAE`
- future-dated official flight support: `ICN` only via `/v1/flight-status` and `tool_get_flight_status`
- remote MCP transport: `streamable-http` mounted at `/mcp`
- HTTP endpoints:
  - `/healthz`
  - `/v1/coverage`
  - `/v1/guide`
  - `/v1/parking`
  - `/v1/flight-status`
  - `/v1/baggage-check`
  - `/v1/customs-rules`
  - `/v1/self-service-options`
  - `/v1/priority-lane-eligibility`
  - `/v1/facilities`
  - `/v1/shops`
  - `/v1/readiness`
- MCP tools:
  - `tool_get_coverage`
  - `tool_get_guide`
  - `tool_get_departure_readiness`
  - `tool_get_parking_status`
  - `tool_get_flight_status`
  - `tool_check_baggage_rules`
  - `tool_get_customs_rules`
  - `tool_get_self_service_options`
  - `tool_get_priority_lane_eligibility`
  - `tool_find_facilities`
  - `tool_find_shops`

## Trust contract
- Every public response includes `source`, `freshness`, `updated_at`, and `coverage_note`.
- Unsupported airports/domains are explicit.
- Forecast data is never labeled as live.
- If a supported live source is unavailable, the API returns a bounded unavailable state instead of guessing.
- ICN parking responses can include fee criteria notes without inventing numeric fee estimates.
- KAC parking responses can include separate `policy_notes` from official discount/reservation guidance.
- KAC readiness can include official processing/crowd signals when coverage exists.
- Future-dated readiness is intentionally out of scope; only `flight-status` supports official future ICN schedules in this wave.

## Quick start

```bash
cp .env.example .env
uv sync --extra dev
uv run departure-ready-api
```

API docs:
- `http://127.0.0.1:8000/docs`
- remote MCP (same process): `http://127.0.0.1:8000/mcp`

Run MCP (stdio):
```bash
uv run departure-ready-mcp
```

Useful environment variables:
- `DEPARTURE_READY_KAC_SERVICE_KEY`
- `DEPARTURE_READY_IIAC_SERVICE_KEY`
- `DEPARTURE_READY_HTTP_TIMEOUT_SEC`
- `DEPARTURE_READY_HTTP_PORT`
- `DEPARTURE_READY_PUBLIC_HTTP_URL`
- `DEPARTURE_READY_PUBLIC_MCP_URL`

Without live service keys, policy endpoints still work and live domains return explicit unavailable states.

Future ICN schedule example:
```bash
curl "http://127.0.0.1:8000/v1/flight-status?airport_code=ICN&travel_date=2026-03-25"
```

`/v1/readiness` stays same-day only and does not accept `travel_date`.

## Render deploy

Render direct deployment is defined in `render.yaml`.

Recommended runtime env:
- `DEPARTURE_READY_ENV=prod`
- `DEPARTURE_READY_PUBLIC_HTTP_URL=https://<your-service>.onrender.com`
- `DEPARTURE_READY_PUBLIC_MCP_URL=https://<your-service>.onrender.com/mcp`
- `DEPARTURE_READY_KAC_SERVICE_KEY`
- `DEPARTURE_READY_IIAC_SERVICE_KEY`

Hosted canary workflow:
- `.github/workflows/canary.yml`
- runs local keyed smoke plus hosted HTTP/MCP checks
- stores reports as GitHub Actions artifacts

## Verification

```bash
uv run pytest
uv run ruff check .
uv run python -m departure_ready.smoke
```

Hosted canary dry-run without public URLs stays bounded:

```bash
uv run python -m departure_ready.smoke --mode hosted
```

Representative release queries live in `tests/test_qa_corpus.py`.
Wave 3 launch/smoke coverage lives in `tests/test_launch_wave2.py`, `tests/test_remote_launch_wave3.py`, and `tests/test_future_flight_surface_wave3.py`.

## Build order
Read in this order:
1. `docs/PRD.md`
2. `docs/EXEC_PLAN.md`
3. `docs/SOURCE_REGISTRY.md`
4. `docs/CODEX_PROMPTS.md`
