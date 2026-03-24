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

## Trust contract
- Every public response includes `source`, `freshness`, `updated_at`, and `coverage_note`.
- Unsupported airports/domains are explicit.
- Forecast data is never labeled as live.
- If a supported live source is unavailable, the API returns a bounded unavailable state instead of guessing.

## Quick start

```bash
cp .env.example .env
uv sync --extra dev
uv run departure-ready-api
```

API docs:
- `http://127.0.0.1:8000/docs`

Run MCP (stdio):
```bash
uv run departure-ready-mcp
```

Useful environment variables:
- `DEPARTURE_READY_KAC_SERVICE_KEY`
- `DEPARTURE_READY_IIAC_SERVICE_KEY`
- `DEPARTURE_READY_HTTP_TIMEOUT_SEC`
- `DEPARTURE_READY_HTTP_PORT`

Without live service keys, policy endpoints still work and live domains return explicit unavailable states.

## Verification

```bash
uv run pytest
uv run ruff check .
```

Representative release queries live in `tests/test_qa_corpus.py`.

## Build order
Read in this order:
1. `docs/PRD.md`
2. `docs/EXEC_PLAN.md`
3. `docs/SOURCE_REGISTRY.md`
4. `docs/CODEX_PROMPTS.md`
