# SOURCE_REGISTRY — official sources for Departure Ready MCP

## Principles
- Official source first
- Preserve source boundaries
- Preserve freshness labels
- Do not guess on live failures
- Prefer airport/operator/public-agency data over blogs or user posts

## Current implementation status
Currently wired into connectors and public services:
- `kac_parking_rt`
- `kac_parking_congestion_rt`
- `kac_parking_discount`
- `kac_parking_reservation`
- `kac_flight_detail_rt`
- `kac_processing_time`
- `kac_crowd_info`
- `iiac_parking_rt`
- `iiac_parking_fee`
- `iiac_t1_parking_slot`
- `iiac_flight_today`
- `iiac_flight_weekly`
- `iiac_passenger_forecast`
- `iiac_facilities`
- `iiac_shops`
- `iiac_baggage_policy`
- `customs_traveler_rules`
- `iiac_smartpass`
- `iiac_self_checkin_bagdrop`
- `iiac_easy_drop`
- `iiac_priority_lane`

Tracked in the registry but not yet exposed in a public service or API route:
- `kac_facility_file`
- `kac_accessibility_file`

## Source tiers
### Tier A — live or near-live operational data
Use first for operational answers.

| key | source | coverage | type | main use |
|---|---|---:|---|---|
| `kac_parking_rt` | KAC nationwide real-time parking | KAC airports | live | available spaces / occupancy summary |
| `kac_parking_congestion_rt` | KAC nationwide parking congestion | KAC airports | live | drive-or-not signal |
| `kac_flight_detail_rt` | KAC real-time flight detail | KAC airports | live | delay/cancel/gate/check-in signals |
| `kac_processing_time` | KAC airport processing time | GMP/CJU | live-ish | queue / time-to-gate signals |
| `kac_crowd_info` | KAC airport crowd info | PUS/CJJ/TAE | live-ish | segment crowd signal |
| `iiac_parking_rt` | IIAC parking info | ICN | live | parking lots / occupancy |
| `iiac_parking_fee` | IIAC parking fee criteria | ICN | daily/static | fee estimation |
| `iiac_t1_parking_slot` | IIAC T1 parking slot status | ICN T1 short-term | live | short-term granular slot data |
| `iiac_flight_today` | IIAC same-day flight operations | ICN | live/today | status, terminal, gate, counters |
| `iiac_flight_weekly` | IIAC weekly flight schedule | ICN | near-term | future departure readiness |
| `iiac_passenger_forecast` | IIAC passenger forecast by departure/arrival zone | ICN | forecast | departure crowd prediction |

## Tier B — facilities and service surfaces
| key | source | coverage | type | main use |
|---|---|---:|---|---|
| `iiac_facilities` | IIAC terminal facilities | ICN | daily | pharmacy, ATM, lounge, nursery, etc. |
| `iiac_shops` | IIAC commercial facilities | ICN | daily | shop lookup by category/name |
| `kac_facility_file` | KAC airport facility file data | KAC airports | static/annual | facility fallback and metadata |
| `kac_accessibility_file` | KAC accessibility facility maps | KAC airports | static-ish | wheelchair / accessibility hints |

## Tier C — policy / rules
| key | source | coverage | type | main use |
|---|---|---:|---|---|
| `iiac_baggage_policy` | Incheon prohibited/restricted items page | generic airport policy | policy | carry-on vs checked guidance |
| `customs_traveler_rules` | Korea Customs traveler goods rules | inbound customs | policy | duty-free threshold / declaration |
| `iiac_smartpass` | Incheon SmartPass page | ICN | policy | fast lane eligibility |
| `iiac_self_checkin_bagdrop` | Incheon self check-in/backdrop page | ICN | policy | airline/time/eligibility |
| `iiac_easy_drop` | Incheon Easy Drop page | ICN | policy | city bag drop eligibility |
| `iiac_priority_lane` | Incheon priority departure lane page | ICN | policy | who can use the priority lane |
| `kac_parking_discount` | KAC parking discount page | KAC airports except ICN note | policy | 다자녀/discount logic |
| `kac_parking_reservation` | KAC parking reservation guide | selected airports | policy | reservation windows / penalty rules |

## Source details

### 1) KAC nationwide real-time parking
- portal id / doc: `15056803`
- purpose: current parking status at KAC airports
- fallback: none
- freshness label: `live`
- notes:
  - used for KAC parking recommendation
  - do not infer missing airports

### 2) KAC nationwide parking congestion
- portal id / doc: `15063437`
- purpose: easier drive/not-drive summary
- freshness label: `live`
- notes:
  - use alongside parking RT, not instead of it

### 3) KAC real-time flight detail
- portal id / doc: `15113771`
- purpose: detailed flight state incl. delay/cancel
- freshness label: `live`
- notes:
  - use airport code + airline/flight filters when possible

### 4) KAC processing time (GMP/CJU)
- portal id / doc: `15095478`
- purpose: total/segment time from check-in to departure
- freshness label: `live`
- notes:
  - suitable for "leave now?" guidance
  - do not generalize to unsupported airports

### 5) KAC crowd info (PUS/CJJ/TAE)
- portal id / doc: `15110019`
- purpose: queue segment crowd
- freshness label: `live`
- notes:
  - keep airport coverage explicit

### 6) IIAC parking info
- portal id / doc: `15095047`
- purpose: ICN live parking overview by lot
- freshness label: `live`
- notes:
  - watch for schema drift and operational changes

### 7) IIAC parking fee criteria
- portal id / doc: `15095053`
- purpose: ICN fee estimator
- freshness label: `daily` or `static`
- notes:
  - quote source text when ambiguous

### 8) IIAC T1 parking slot status
- portal id / doc: `15107228`
- purpose: T1 short-term slot granularity
- freshness label: `live`
- notes:
  - currently T1 short-term only, do not overclaim T2 parity

### 9) IIAC same-day / weekly flight operations
- portal ids / docs:
  - same-day: `15095093`
  - weekly: `15095074`
- purpose: ICN flight lookup and future readiness
- freshness label: `live` / `near-term`
- notes:
  - use same-day first, weekly as future fallback
  - weekly exposure is limited to `flight-status`; readiness remains same-day only

### 10) IIAC passenger forecast by zone
- portal id / doc: `15095066`
- purpose: forecasted departure-area congestion by terminal/zone
- freshness label: `forecast`
- notes:
  - label as forecast, not real-time

### 11) IIAC facilities
- portal id / doc: `15095064`
- purpose: official facility lookup
- freshness label: `daily`
- notes:
  - supports category/name/terminal/in-out/floor filters

### 12) IIAC shops
- portal id / doc: `15095043`
- purpose: commercial store lookup
- freshness label: `daily`
- notes:
  - use for pharmacy / convenience / telecom / exchange style store needs

### 13) Baggage / restricted items
- official page: Incheon restricted items
- purpose: carry-on / checked baseline policy
- freshness label: `policy`
- notes:
  - separate from customs rules
  - separate domestic vs international where source does

### 14) Customs traveler goods rules
- official page: Korea Customs traveler goods rules + expected tax calculator
- purpose: declaration / duty-free threshold guidance
- freshness label: `policy`
- notes:
  - do not pretend this is airline baggage policy
  - clarify that final enforcement depends on customs inspection

### 15) SmartPass / self check-in / easy drop / priority lane
- official pages: Incheon airport service pages
- purpose: eligibility and availability logic
- freshness label: `policy`
- notes:
  - keep airline-specific constraints structured
  - keep ICN-only labeling explicit where applicable

## Freshness mapping rules
- real-time API -> `live`
- forecast / passenger prediction -> `forecast`
- daily-refreshed operation metadata -> `daily`
- rarely changing airport metadata / file data -> `static`
- text rules / public policy pages -> `policy`

## Unsupported-coverage rules
- If a query asks for ICN-only service at a KAC airport, say unsupported.
- If a query asks for live crowd at an airport without live crowd coverage, do not approximate from schedules.
- If a query asks for parking fee calculation without enough inputs, return a bounded or partial result and say what is missing.

## Drift watchlist
- IIAC parking APIs have changed operationally before; add canary checks.
- KAC airport-specific reservation policies may diverge by airport.
- Self-service airline eligibility pages can change without API version changes.
