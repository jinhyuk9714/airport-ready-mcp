# QA plan

## Goal
Prevent confident-but-wrong travel guidance.

## Test layers

### 1. unit
- airport alias normalization
- response envelope construction
- freshness mapping
- baggage classification table behavior
- service eligibility rule branches

### 2. connector contract
- response parsing per source
- missing field handling
- empty results handling
- live timeout handling

### 3. service logic
- ICN readiness card with flight + parking + baggage
- GMP readiness card with processing time + parking
- unsupported-airport service denial
- forecast vs live labeling

### 4. API smoke
- `/healthz`
- `/docs`
- `/v1/coverage`
- `/v1/guide`
- `/v1/parking`
- `/v1/flight-status`
- `/v1/baggage-check`
- `/v1/customs-rules`
- `/v1/self-service-options`
- `/v1/priority-lane-eligibility`
- `/v1/facilities`
- `/v1/readiness`

### 5. MCP smoke
- stdio boot
- remote `/mcp` mount
- coverage tool
- guide tool
- readiness / parking / baggage / customs tools
- shops tool parity with HTTP `/v1/shops`

### 6. Launch smoke
- no-key bounded-unavailable smoke runner
- keyed canary skip behavior
- hosted canary dry-run without public URLs
- API app boot smoke
- MCP stdio no-stdout-pollution smoke

## Release corpus categories
1. parking status
2. flight status
3. baggage edge cases
4. customs edge cases
5. fast service eligibility
6. facility lookup
7. unsupported coverage
8. source outage / timeout behavior

Automated corpus:
- `tests/test_qa_corpus.py`
- `tests/test_policy_services.py`
- `tests/test_live_services.py`
- `tests/test_readiness_wave2.py`
- `tests/test_surface_wave2.py`
- `tests/test_launch_wave2.py`
- `tests/test_future_flight_wave3.py`
- `tests/test_future_flight_surface_wave3.py`
- `tests/test_parking_wave3.py`
- `tests/test_remote_launch_wave3.py`

## Edge cases to include
- international liquid 100ml rule
- domestic no liquid limit note
- kimchi / gochujang
- battery ambiguity
- ICN-only SmartPass queried for GMP
- future ICN weekly flight without gate/check-in fields
- future non-ICN flight query returns explicit unsupported coverage
- live source unavailable but static policy still available

## Release gate
No launch if:
- any output labels forecast as live
- baggage/customs semantics are mixed
- unsupported airports are silently treated as supported
- live timeouts return fabricated values
