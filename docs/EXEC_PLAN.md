# EXEC_PLAN — Codex implementation order

## Phase 0 — bootstrap
Goal:
- installable project
- health endpoint
- importable package
- passing baseline tests

Tasks:
- settings
- response envelope
- support matrix
- FastAPI app factory
- minimal FastMCP server with coverage tools

Done when:
- `uv run pytest` passes
- `uv run departure-ready-api` starts
- `uv run departure-ready-mcp` starts

---

## Phase 1 — contracts and domain models
Goal:
- data contracts stable before connector work

Tasks:
- AirportCode enum
- Freshness enum
- SourceRef, ResponseMeta, Envelope
- ReadinessCard, ParkingSnapshot, FlightSnapshot, BaggageDecision, ServiceEligibility
- normalized airport aliases

Done when:
- schemas are documented in `docs/MCP_API_SPEC.md`
- model unit tests exist

---

## Phase 2 — official connectors
Goal:
- source adapters exist with normalization boundaries

Priority order:
1. KAC parking
2. KAC parking congestion
3. KAC flight info
4. KAC processing/crowd
5. IIAC parking / fee / flight / crowd
6. IIAC facilities / shops
7. policy sources: baggage / customs / service eligibility

Done when:
- every adapter returns typed domain objects
- every adapter stamps `source` + `updated_at`
- live failure surfaces rich error context

---

## Phase 3 — core services
Goal:
- merge source data into user-facing answers

Tasks:
- parking decision service
- baggage decision service
- customs guidance service
- self-service eligibility service
- readiness card aggregator
- facility search service

Done when:
- services hide connector differences
- unsupported airport logic is centralized
- tests cover merge/fallback behavior

---

## Phase 4 — HTTP API
Goal:
- public JSON surface exists

Endpoints in first wave:
- `GET /healthz`
- `GET /v1/coverage`
- `GET /v1/guide`
- `GET /v1/parking`
- `GET /v1/flight-status`
- `GET /v1/baggage-check`
- `GET /v1/customs-rules`
- `GET /v1/self-service-options`
- `GET /v1/facilities`
- `GET /v1/readiness`

Done when:
- OpenAPI docs render cleanly
- envelope contract is consistent
- errors preserve domain semantics

---

## Phase 5 — MCP surface
Goal:
- tools and resources reflect the same public contract

Resources:
- `departure://guide`
- `departure://coverage`
- `departure://baggage-policy`
- `departure://customs-policy`
- `departure://service-matrix`

Tools:
- `tool_get_departure_readiness`
- `tool_get_parking_status`
- `tool_estimate_parking_fee`
- `tool_get_flight_status`
- `tool_check_baggage_rules`
- `tool_get_customs_rules`
- `tool_get_self_service_options`
- `tool_get_priority_lane_eligibility`
- `tool_find_facilities`
- `tool_find_shops`

Done when:
- stdio server works in an MCP host
- tool outputs match HTTP contract semantics
- no stdout logging in stdio mode

---

## Phase 6 — QA and launch
Goal:
- release pack and canaries exist

Artifacts:
- smoke queries
- airport coverage QA pack
- baggage/customs edge-case pack
- source outage behavior pack
- README final draft

Launch bar:
- ICN + GMP canaries pass
- no critical baggage/customs regressions
- no unlabeled stale/live confusion
