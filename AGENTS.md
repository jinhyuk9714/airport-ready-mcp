# AGENTS.md

## Repository mission
Build **Departure Ready MCP** as a student-quality but production-minded **travel readiness** product:
- **Primary surface**: read-only Remote MCP
- **Companion surface**: HTTP API
- **Core user promise**: answer "Can I leave for the airport now?", "Should I drive?", "Can I carry this item?", "Can I use faster airport services?" using **official sources only**.

## V1 scope
Strong support:
- ICN (Incheon)
- GMP (Gimpo)
- CJU (Jeju)
- PUS / CJJ / TAE for selected crowd/wait signals where official coverage exists

Core flows:
1. departure readiness card
2. parking decision
3. baggage / carry-on / checked guidance
4. customs / duty-free threshold guidance
5. fast service eligibility (self check-in, smart pass, priority lane, easy drop)
6. airport facility / shop lookup

## Out of scope for V1
- turn-by-turn navigation
- generic maps / nearby restaurants / taxi comparison
- non-official crowd estimation
- personal itinerary sync
- booking / payment / account creation
- outbound international policy guessing based on blogs or social posts

## Source policy
- Use **official airport / customs / public data** first.
- Every domain object must carry:
  - `source`
  - `freshness`
  - `updated_at`
  - `coverage_note`
- If live fetch fails, return a clear unavailable state. **Do not guess.**
- Distinguish:
  - `live`
  - `forecast`
  - `daily`
  - `static`
  - `policy`

## Output contract
All API/MCP responses must make the trust boundary explicit.
Use the response envelope defined in `src/departure_ready/contracts.py`.

Required principles:
- never hide unsupported airports
- never present "estimated" as "live"
- never mix customs rules and airline baggage rules without labeling them separately
- never collapse airport-specific policy differences into one generic answer

## Codex workflow rules
When you work in this repo:
1. Read `docs/PRD.md`, `docs/EXEC_PLAN.md`, and `docs/SOURCE_REGISTRY.md` before major edits.
2. Implement in this order unless the current task explicitly narrows scope:
   - contracts / models
   - connectors
   - services
   - API
   - MCP
   - QA / docs
3. Prefer small, reviewable commits.
4. After code edits, run:
   - `uv run pytest`
   - `uv run ruff check .`
5. Update docs when public behavior changes.

## Engineering rules
- Python 3.11+
- Type hints required for public functions
- Prefer Pydantic models for request/response shapes
- Put connector-specific normalization close to each connector
- Put cross-source merge logic in services, not in routes
- Keep airport code aliases centralized
- No stdout logging inside STDIO MCP server; use stderr/logging only

## Directory conventions
- `src/departure_ready/connectors/`: official source adapters
- `src/departure_ready/services/`: cross-source orchestration
- `src/departure_ready/api/`: FastAPI routes and schemas
- `src/departure_ready/mcp/`: FastMCP server
- `docs/`: product, source, QA, rollout docs
- `.agents/skills/`: task-scoped Codex skills

## Done criteria for V1
A change is not done unless:
- tests pass
- response envelope fields are present
- source/freshness semantics are correct
- unsupported coverage is documented
- at least one realistic user query is added to docs or QA corpus if behavior changed
