# Codex prompt pack

Use these prompts in order. Before each prompt, start Codex in the repo root.

Recommended CLI posture:
```bash
codex --sandbox workspace-write --ask-for-approval on-request
```

---

## 01 — bootstrap the repo
Read `AGENTS.md`, `docs/PRD.md`, `docs/EXEC_PLAN.md`, and `docs/SOURCE_REGISTRY.md`.
Then review the existing scaffold and make the repo boot cleanly:
- verify imports
- make `uv run pytest` pass
- make `uv run departure-ready-api` start
- make `uv run departure-ready-mcp` start
Do not add product features yet. Only stabilize the scaffold and explain what is still a placeholder.

---

## 02 — harden contracts and models
Read `AGENTS.md` and `docs/MCP_API_SPEC.md`.
Implement or refine:
- freshness enum
- source reference model
- response envelope
- airport support matrix models
- flight / parking / baggage / customs / service eligibility / facility models
Add tests for serialization and envelope consistency.
Then run tests and lint.

---

## 03 — airport normalization and support matrix
Implement:
- airport code aliases
- terminal aliases
- support matrix registry
- unsupported coverage helper
Expose this through both API and MCP.
Add tests for alias normalization and unsupported coverage behavior.

---

## 04 — official connectors skeleton
Implement typed connectors for:
- KAC parking
- KAC parking congestion
- KAC flight detail
- KAC processing/crowd
- IIAC parking / fee / flight / passenger forecast / facilities / shops
Do not overbuild service logic yet.
Focus on:
- typed request/response parsing
- timeout/retry
- clear source IDs
- connector tests with mocked HTTP responses

---

## 05 — parking domain
Implement parking service and `/v1/parking`.
Behavior:
- merge KAC or IIAC live status into one normalized parking snapshot
- optionally estimate fees when enough info exists
- label gaps clearly
- never guess unknown lots
Add tests for ICN vs KAC branching and for unsupported airports.

---

## 06 — flight and readiness core
Implement:
- flight status service
- readiness card skeleton
- `/v1/flight-status`
- `/v1/readiness` basic version
The readiness card must include:
- current or forecast operational signal
- parking recommendation if requested
- next actions
- explicit coverage note
Do not implement baggage/customs yet.

---

## 07 — baggage and customs
Implement:
- baggage rule classification
- customs guidance classification
- `/v1/baggage-check`
- `/v1/customs-rules`
Rules:
- keep baggage and customs separate
- support ambiguity / manual-confirmation states
- preserve domestic vs international distinction when the source does
Add edge-case tests for liquids, kimchi/gochujang, alcohol, perfume, cigarettes, declaration threshold notes.

---

## 08 — fast services / eligibility
Implement:
- smart pass eligibility
- self check-in / self bag drop availability
- easy drop eligibility
- priority lane eligibility
- `/v1/self-service-options`
- `/v1/priority-lane-eligibility`
Keep airport-specific rules explicit. Do not generalize ICN-only services to KAC airports.

---

## 09 — facilities and shops
Implement:
- `/v1/facilities`
- optional `/v1/shops`
Use IIAC facility/shop sources first.
For KAC airports, use only what is actually covered by official sources.
Return structured location text and operating info where available.

---

## 10 — MCP build-out
Expand the MCP server to expose:
- `tool_get_departure_readiness`
- `tool_get_parking_status`
- `tool_get_flight_status`
- `tool_check_baggage_rules`
- `tool_get_customs_rules`
- `tool_get_self_service_options`
- `tool_get_priority_lane_eligibility`
- `tool_find_facilities`
Also expose guide/coverage/policy resources if supported cleanly by the SDK version in use.
Keep MCP tool outputs short and structured.

---

## 11 — QA pass
Create:
- smoke corpus
- baggage/customs edge corpus
- coverage mismatch corpus
- source outage corpus
Add a small smoke runner if useful.
Then run tests, lint, and summarize remaining risks.

---

## 12 — launch docs
Polish:
- README
- source registry
- quickstart
- environment docs
- known limitations
Make sure the docs exactly match the current implementation.
