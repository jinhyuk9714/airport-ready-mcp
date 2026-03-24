# MCP + HTTP API spec

## Response envelope

```json
{
  "ok": true,
  "meta": {
    "source": [
      {
        "name": "kac_parking_rt",
        "kind": "official_api",
        "url": "https://www.data.go.kr/data/15056803/openapi.do"
      }
    ],
    "freshness": "live",
    "updated_at": "2026-03-23T10:00:00+09:00",
    "coverage_note": "KAC airport live parking status"
  },
  "data": {}
}
```

## Common enums
- `freshness`: `live | forecast | daily | static | policy`
- `airport_code`: `ICN | GMP | CJU | PUS | CJJ | TAE | ...`

---

## HTTP endpoints

### `GET /healthz`
Liveness probe.

### `GET /v1/coverage`
Returns support matrix and trust contract.

### `GET /v1/guide`
Returns product guide, scope, and domain boundaries.

### `GET /v1/parking`
Query:
- `airport_code`
- `terminal` optional

Returns:
- lot states
- `fee_note` enrichment for ICN lots when official fee criteria are available
- congestion summary
- explicit unavailable state when live parking data cannot be fetched

### `GET /v1/flight-status`
Query:
- `airport_code`
- `flight_no` optional

Returns:
- scheduled / changed time
- terminal
- gate
- counters
- status

### `GET /v1/baggage-check`
Query:
- `trip_type=domestic|international`
- `item_query`
- `battery_wh` optional
- `liquid_ml` optional

Returns:
- decision category
- carry_on_allowed
- checked_allowed
- declaration/warning notes
- ambiguity flag

### `GET /v1/customs-rules`
Query:
- `item_query` optional
- `purchase_value_usd` optional
- `alcohol_liters` optional
- `perfume_ml` optional
- `cigarette_count` optional

Returns:
- base threshold summary
- declaration hint
- reduced tax self-report note
- warnings

### `GET /v1/self-service-options`
Query:
- `airport_code`
- `airline`

Returns:
- smart_pass_supported
- self_checkin_supported
- self_bag_drop_supported
- easy_drop_supported
- notes / limits

### `GET /v1/priority-lane-eligibility`
Query:
- `airport_code`
- `user_profile` free-form or structured flags

Returns:
- eligible
- evidence
- required documents

### `GET /v1/facilities`
Query:
- `airport_code`
- `terminal` optional
- `category` optional
- `query` optional

Returns:
- matched facilities
- category
- location text
- operating hours
- phone

### `GET /v1/shops`
Query:
- `airport_code`
- `terminal` optional
- `category` optional
- `query` optional

Returns:
- matched shops
- category
- location text
- operating hours
- phone

### `GET /v1/readiness`
Query:
- `airport_code`
- `flight_no` optional
- `going_by_car` optional
- `items` optional repeated
- `traveler_flags` optional repeated

Returns:
- readiness card
- `operational_signals` when official KAC processing/crowd coverage exists
- next actions
- parking recommendation
- service eligibility
- baggage warnings
- terminal/service lookup hints

---

## MCP tools
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

## MCP tool output rule
Tool outputs should stay structured and short.
Prefer JSON-like dict outputs over long prose. Let the client model write prose.
If a live source is unavailable, return a bounded unavailable payload rather than guessed values.
