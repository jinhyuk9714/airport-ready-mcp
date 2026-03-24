---
name: response-contract
description: Use this skill when a task touches API responses, MCP tool outputs, schemas, envelopes, or error handling.
---

Rules:
- Every public response must include `source`, `freshness`, `updated_at`, `coverage_note`.
- `forecast` must never be labeled `live`.
- `policy` outputs must not masquerade as operational facts.
- Ambiguous baggage/customs cases should produce a bounded answer plus a warning note.
- Prefer short structured payloads for MCP tools.
