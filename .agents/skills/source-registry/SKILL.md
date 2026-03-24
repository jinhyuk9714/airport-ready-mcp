---
name: source-registry
description: Use this skill when a task touches connectors, data freshness, airport coverage, or official-source selection. Do not use it for pure UI copy edits.
---

Read `docs/SOURCE_REGISTRY.md` before changing connector logic.

Checklist:
1. Confirm the source tier and freshness class.
2. Keep airport-specific coverage explicit.
3. Do not merge policy and live data without labels.
4. Record unsupported cases in `coverage_note`.
5. Add or update a source note if implementation behavior changes.
