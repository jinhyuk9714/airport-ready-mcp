from __future__ import annotations

import asyncio

from departure_ready.catalog import CATALOG_SOURCE, normalize_airport_code
from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.kac_processing import KacProcessingConnector
from departure_ready.contracts import Envelope, Freshness, merge_response_meta
from departure_ready.domain.models import (
    FacilityMatch,
    OperationalSignal,
    ReadinessCard,
    ServiceEligibility,
)
from departure_ready.services.baggage import build_baggage_decision
from departure_ready.services.facilities import build_facilities_envelope
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
    operational_signals, signal_notes = _load_kac_operational_signals(normalized_airport, settings)
    facility_hints, facility_notes = _load_facility_hints(
        normalized_airport,
        traveler_flags or [],
        settings,
    )

    flight = None
    operational_signal = "unavailable"
    summary = f"{normalized_airport} readiness is bounded by current official-source coverage."
    next_actions = ["Review flight status before leaving for the airport."]
    trust_items = [*baggage_warnings, *service_eligibility, *operational_signals, *facility_hints]

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

    if operational_signals:
        summary = _append_operational_signal_summary(summary, operational_signals)
        next_actions.extend(_operational_signal_actions(operational_signals))
    if signal_notes:
        next_actions.extend(signal_notes)
    if facility_notes:
        next_actions.extend(facility_notes)

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
    if signal_notes:
        meta.coverage_note = f"{meta.coverage_note} | {' | '.join(signal_notes)}"
    card = ReadinessCard(
        airport_code=normalized_airport,
        summary=summary,
        operational_signal=operational_signal,
        operational_signals=operational_signals,
        next_actions=list(dict.fromkeys(next_actions)),
        flight=flight,
        parking=parking,
        baggage_warnings=baggage_warnings,
        service_eligibility=service_eligibility,
        facility_hints=facility_hints,
        source=meta.source,
        freshness=meta.freshness,
        updated_at=meta.updated_at,
        coverage_note=meta.coverage_note,
    )
    return Envelope(meta=meta, data=card)


def _load_kac_operational_signals(
    airport_code: str,
    settings: Settings,
) -> tuple[list[OperationalSignal], list[str]]:
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    if normalized_airport not in {"GMP", "CJU", "PUS", "CJJ", "TAE"}:
        return [], []

    context = ConnectorContext(
        timeout_sec=settings.http_timeout_sec,
        default_headers={"User-Agent": "departure-ready-mcp/0.1.0"},
        max_retries=settings.http_max_retries,
    )
    connector = KacProcessingConnector(context, settings.kac_service_key)
    note_label = "processing signal" if normalized_airport in {"GMP", "CJU"} else "crowd signal"

    try:
        if normalized_airport in {"GMP", "CJU"}:
            signal = _await_if_needed(connector.get_processing_signal(normalized_airport))
        else:
            signal = _await_if_needed(connector.get_crowd_signal(normalized_airport))
    except Exception:  # noqa: BLE001
        return [], [f"Official KAC {note_label} unavailable for {normalized_airport}."]

    if signal is None:
        return [], [f"Official KAC {note_label} unavailable for {normalized_airport}."]

    return [signal], []


def _await_if_needed(result):
    if hasattr(result, "__await__"):
        return asyncio.run(result)
    return result


def _append_operational_signal_summary(
    summary: str,
    signals: list[OperationalSignal],
) -> str:
    signal_bits = [
        f"{signal.airport_code} {signal.signal_type.replace('_', ' ')}: {signal.headline}"
        for signal in signals
    ]
    return f"{summary} Operational signals: {'; '.join(signal_bits)}."


def _operational_signal_actions(signals: list[OperationalSignal]) -> list[str]:
    actions: list[str] = []
    for signal in signals:
        if signal.signal_type == "processing_time":
            actions.append(
                f"Use the official processing time signal for {signal.airport_code}: "
                f"{signal.headline}."
            )
        elif signal.signal_type == "crowd_info":
            actions.append(
                f"Use the official crowd signal for {signal.airport_code}: "
                f"{signal.headline}."
            )
    return actions


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


def _load_facility_hints(
    airport_code: str,
    traveler_flags: list[str],
    settings: Settings,
) -> tuple[list[FacilityMatch], list[str]]:
    categories = _facility_hint_categories(traveler_flags)
    if not categories:
        return [], []

    hints: list[FacilityMatch] = []
    try:
        for category in categories:
            envelope = _await_if_needed(
                build_facilities_envelope(
                    settings,
                    airport_code,
                    category=category,
                )
            )
            if not envelope.ok:
                return [], [f"Official facility lookup unavailable for {airport_code}."]
            for match in envelope.data.matches:
                if _facility_hint_key(match) in {_facility_hint_key(item) for item in hints}:
                    continue
                hints.append(match)
                if len(hints) >= 3:
                    return hints[:3], []
    except Exception:  # noqa: BLE001
        return [], [f"Official facility lookup unavailable for {airport_code}."]

    return hints[:3], []


def _facility_hint_categories(traveler_flags: list[str]) -> list[str]:
    normalized_flags = {flag.strip().lower() for flag in traveler_flags if flag.strip()}
    categories: list[str] = []
    if normalized_flags & {"disabled", "wheelchair", "mobility_impaired", "accessibility"}:
        categories.extend(["accessibility", "medical", "parking"])
    if normalized_flags & {"pregnant", "infant", "child", "medical"}:
        categories.extend(["nursery", "family", "medical", "restroom"])
    return list(dict.fromkeys(categories))


def _facility_hint_key(match: FacilityMatch) -> tuple[str, str | None, str, str, str]:
    return (
        match.airport_code,
        match.terminal,
        match.name,
        match.location_text,
        match.category,
    )
