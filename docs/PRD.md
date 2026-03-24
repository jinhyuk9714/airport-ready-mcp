# PRD — Departure Ready MCP

## 1. Product summary
Departure Ready MCP is a **consumer travel-readiness product** for Korean airports.
It is not a map clone. It solves the final-decision layer before departure:
- go now / wait / leave earlier
- drive / not drive
- carry-on / checked / 신고 필요
- use fast services / not eligible
- where to go inside the airport

## 2. Why this product
Generic map apps are already strong at routes and POIs.
They are weaker at combining:
- real-time parking
- airport queue or crowd signals
- flight state
- airport-specific self-service policies
- baggage restrictions
- customs rules
- terminal facility lookup

This product competes on **official, structured, actionable readiness**.

## 3. Target users
### Primary
- Korean outbound travelers
- airport drop-off / pick-up helpers
- infrequent travelers with anxiety near departure time
- families managing baggage / parking / priority lanes

### Secondary
- frequent travelers who want one readiness card before leaving home
- airport content creators / bloggers who want official data references

## 4. Jobs to be done
1. "Tell me if I can leave now."
2. "Tell me whether I should drive."
3. "Tell me if this item belongs in carry-on or checked baggage."
4. "Tell me whether I can use faster airport flows."
5. "Find the right facility or shop in the airport."

## 5. V1 scope
### Strong support
- ICN
- GMP
- CJU
- selected crowd/wait support for PUS / CJJ / TAE

### Core domains
- flight readiness summary
- parking status / congestion / fee estimate
- baggage rules
- customs / duty-free thresholds
- self-service options
- priority lane eligibility
- facility / shop lookup

## 6. Non-goals
- generic route planning
- outbound visa or entry requirement interpretation
- travel insurance recommendations
- airport shopping deals / recommendations
- OCR-first baggage image classification in V1
- user account / bookings / ticket purchasing

## 7. Core product objects
- Airport
- FlightQuery
- FlightSnapshot
- ParkingSnapshot
- CrowdSnapshot
- BaggageDecision
- CustomsGuidance
- ServiceEligibility
- FacilityMatch
- ReadinessCard

## 8. UX principles
- one screen, next action first
- official source first
- freshness visible everywhere
- unsupported coverage explicitly labeled
- airport-specific policy differences preserved

## 9. Reliability contract
Every public answer must include:
- source
- freshness
- updated_at
- coverage_note

Freshness enum:
- `live`
- `forecast`
- `daily`
- `static`
- `policy`

If a live source fails:
- do not infer
- do not backfill with old values unless the product says `stale`
- say which source is unavailable

## 10. Support matrix
### ICN
- flight: strong
- parking: strong
- crowd forecast: strong
- facilities / shops: strong
- baggage/customs/service policy: strong

### GMP / CJU
- flight: medium/strong
- parking: strong
- processing time: strong
- baggage/customs: policy strong
- facilities: medium

### PUS / CJJ / TAE
- flight: medium
- parking: strong if KAC data works
- crowd/wait: selected support
- baggage/customs: policy strong
- facilities: weak/medium

## 11. Success metrics
Product metrics:
- readiness card generation success rate
- median response latency by domain
- live-source failure rate
- baggage decision disagreement rate from QA corpus
- parking recommendation coverage by airport

User metrics:
- % queries answered without follow-up
- % queries with at least one explicit next action
- % answers with freshness/source shown

## 12. Launch bar
V1 can launch when:
- health/readiness endpoints are stable
- live canary queries pass for ICN + GMP
- baggage/customs corpus has no critical wrong answers
- every live domain exposes freshness + source metadata
- README and source registry match actual implementation
