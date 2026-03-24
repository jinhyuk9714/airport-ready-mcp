from __future__ import annotations

from departure_ready.catalog import CATALOG_SOURCE, normalize_airport_code
from departure_ready.contracts import Envelope, Freshness, merge_response_meta
from departure_ready.domain.models import ReadinessCard, ServiceEligibility
from departure_ready.services.baggage import build_baggage_decision
from departure_ready.services.flight import FlightPayload, build_flight_envelope
from departure_ready.services.parking import build_parking_envelope
from departure_ready.services.self_service import (
    build_priority_lane_eligibility,
    build_self_service_options,
)
from departure_ready.settings import Settings, get_settings


def build_readiness_envelope(
    airport_code: str,
    *,
    flight_no: str | None = None,
    going_by_car: bool = False,
    items: list[str] | None = None,
    traveler_flags: list[str] | None = None,
    settings: Settings | None = None,
) -> Envelope[ReadinessCard]:
    settings = settings or get_settings()
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()

    flight_envelope = build_flight_envelope(
        normalized_airport,
        flight_no=flight_no,
        settings=settings,
    )
    parking_envelope = (
        build_parking_envelope(normalized_airport, settings=settings) if going_by_car else None
    )

    baggage_warnings = [build_baggage_decision(item, "international") for item in (items or [])]
    service_eligibility = _build_service_eligibility(normalized_airport, traveler_flags or [])

    flight = None
    operational_signal = "unavailable"
    summary = f"{normalized_airport} readiness is bounded by current official-source coverage."
    next_actions = ["Review flight status before leaving for the airport."]
    trust_items = [*baggage_warnings, *service_eligibility]

    if flight_envelope.ok:
        flight_payload: FlightPayload = flight_envelope.data
        flight = flight_payload.selected_flight
        operational_signal = flight_payload.status
        summary = flight_payload.summary
        if flight:
            trust_items.append(flight)
        if flight_payload.status == "forecast":
            next_actions.append(
                "Allow extra buffer because only forecast operational data is available."
            )
        elif flight_payload.status == "unavailable":
            next_actions.append(
                "Official flight status is unavailable, so verify with the airport or airline."
            )

    parking = None
    if parking_envelope is not None and parking_envelope.ok:
        parking = parking_envelope.data
        trust_items.extend(parking.lots)
        next_actions.append(parking.recommendation)
    elif going_by_car:
        next_actions.append(
            "Parking status is unavailable; consider leaving earlier or using transit."
        )

    if not baggage_warnings and items:
        next_actions.append("Some baggage items could not be classified; confirm with the airline.")
    elif baggage_warnings:
        next_actions.append(
            "Keep baggage and customs checks separate from airport live operations."
        )

    meta = merge_response_meta(
        trust_items,
        default_note=summary,
        default_source=[CATALOG_SOURCE],
        default_freshness=Freshness.STATIC,
    )
    card = ReadinessCard(
        airport_code=normalized_airport,
        summary=summary,
        operational_signal=operational_signal,
        next_actions=list(dict.fromkeys(next_actions)),
        flight=flight,
        parking=parking,
        baggage_warnings=baggage_warnings,
        service_eligibility=service_eligibility,
        facility_hints=[],
        source=meta.source,
        freshness=meta.freshness,
        updated_at=meta.updated_at,
        coverage_note=meta.coverage_note,
    )
    return Envelope(meta=meta, data=card)


def _build_service_eligibility(
    airport_code: str,
    traveler_flags: list[str],
) -> list[ServiceEligibility]:
    options = build_self_service_options(airport_code)
    priority = build_priority_lane_eligibility(airport_code, traveler_flags=traveler_flags)

    return [
        ServiceEligibility(
            airport_code=options.airport_code,
            service_name="smart_pass",
            eligible=options.smart_pass_supported,
            reason="ICN SmartPass policy status.",
            evidence=options.notes,
            source=options.source,
            freshness=options.freshness,
            updated_at=options.updated_at,
            coverage_note=options.coverage_note,
        ),
        ServiceEligibility(
            airport_code=options.airport_code,
            service_name="self_checkin",
            eligible=options.self_checkin_supported,
            reason="ICN self check-in policy status.",
            evidence=options.notes,
            source=options.source,
            freshness=options.freshness,
            updated_at=options.updated_at,
            coverage_note=options.coverage_note,
        ),
        ServiceEligibility(
            airport_code=priority.airport_code,
            service_name="priority_lane",
            eligible=priority.eligible,
            reason=priority.reason,
            evidence=priority.evidence,
            required_documents=priority.required_documents,
            source=priority.source,
            freshness=priority.freshness,
            updated_at=priority.updated_at,
            coverage_note=priority.coverage_note,
        ),
    ]
