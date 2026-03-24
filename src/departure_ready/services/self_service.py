from __future__ import annotations

from datetime import UTC, datetime

from departure_ready.catalog import normalize_airport_code
from departure_ready.connectors.policy import (
    IIAC_EASY_DROP,
    IIAC_PRIORITY_LANE,
    IIAC_SELF_CHECKIN,
    IIAC_SMARTPASS,
)
from departure_ready.contracts import Envelope, Freshness
from departure_ready.domain.models import PriorityLaneEligibility, SelfServiceOptions
from departure_ready.services.common import envelope_from_model

ICN_ONLY_NOTES = (
    "Smart Pass, self check-in, Easy Drop, and priority lane services are ICN-only in this repo.",
    "Confirm the airline and terminal because eligibility can change by route "
    "and operational setup.",
)

PRIORITY_FLAGS = {
    "mobility_impaired": "traveler accompanied by the mobility impaired",
    "pregnant": "pregnant traveler",
    "infant": "traveler with an infant",
    "child": "traveler with children",
    "children": "traveler with children",
    "medical": "medical or accessibility need",
    "disabled": "accessibility need",
}


def build_self_service_options(airport_code: str, airline: str | None = None) -> SelfServiceOptions:
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    now = datetime.now(UTC)

    if normalized_airport != "ICN":
        return SelfServiceOptions(
            airport_code=normalized_airport,
            airline=airline,
            smart_pass_supported=False,
            self_checkin_supported=False,
            self_bag_drop_supported=False,
            easy_drop_supported=False,
            notes=list(ICN_ONLY_NOTES),
            source=IIAC_SMARTPASS.source() + IIAC_SELF_CHECKIN.source() + IIAC_EASY_DROP.source(),
            freshness=Freshness.POLICY,
            updated_at=now,
            coverage_note="ICN-only self-service policies do not apply at KAC airports.",
        )

    notes = [
        "Self-service eligibility is airline-specific; verify the airline's check-in rules.",
        "Easy Drop only works when the airline supports the related self check-in flow.",
    ]
    if airline:
        notes.append(f"Airline provided: {airline}.")

    return SelfServiceOptions(
        airport_code=normalized_airport,
        airline=airline,
        smart_pass_supported=True,
        self_checkin_supported=True,
        self_bag_drop_supported=True,
        easy_drop_supported=True,
        notes=notes,
        source=(
            IIAC_SMARTPASS.source()
            + IIAC_SELF_CHECKIN.source()
            + IIAC_EASY_DROP.source()
            + IIAC_PRIORITY_LANE.source()
        ),
        freshness=Freshness.POLICY,
        updated_at=now,
        coverage_note="Official Incheon self-service policy; airline-specific rules still apply.",
    )


def build_priority_lane_eligibility(
    airport_code: str,
    traveler_flags: list[str] | None = None,
) -> PriorityLaneEligibility:
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    now = datetime.now(UTC)
    flags = {flag.strip().lower() for flag in (traveler_flags or []) if flag.strip()}

    if normalized_airport != "ICN":
        return PriorityLaneEligibility(
            airport_code=normalized_airport,
            eligible=False,
            reason="Priority lane is an ICN-only service in this product.",
            evidence=["KAC airports are not covered by the official Incheon priority lane policy."],
            required_documents=[],
            source=IIAC_PRIORITY_LANE.source(),
            freshness=Freshness.POLICY,
            updated_at=now,
            coverage_note=(
                "Priority lane is an ICN-only policy and is not supported at KAC airports."
            ),
        )

    matched = [PRIORITY_FLAGS[flag] for flag in flags if flag in PRIORITY_FLAGS]
    if matched:
        return PriorityLaneEligibility(
            airport_code=normalized_airport,
            eligible=True,
            reason="Traveler profile matches the official priority lane categories.",
            evidence=matched,
            required_documents=[
                "Verify identity and travel documents at the airport check-in or gate area.",
            ],
            source=IIAC_PRIORITY_LANE.source(),
            freshness=Freshness.POLICY,
            updated_at=now,
            coverage_note="Official Incheon priority lane policy.",
        )

    return PriorityLaneEligibility(
        airport_code=normalized_airport,
        eligible=None,
        reason=(
            "Traveler profile is incomplete. Confirm whether the passenger fits "
            "an official priority category."
        ),
        evidence=[
            (
                "Official categories include travelers with mobility needs, "
                "pregnant travelers, and families with young children."
            ),
        ],
        required_documents=[
            "Bring any supporting documents or accessibility needs proof the airline requests.",
        ],
        source=IIAC_PRIORITY_LANE.source(),
        freshness=Freshness.POLICY,
        updated_at=now,
        coverage_note=(
            "Official Incheon priority lane policy requires traveler profile confirmation."
        ),
    )


def build_self_service_envelope(
    airport_code: str,
    airline: str | None = None,
) -> Envelope[SelfServiceOptions]:
    options = build_self_service_options(airport_code, airline=airline)
    return envelope_from_model(options, options)


def build_priority_lane_envelope(
    airport_code: str,
    traveler_flags: list[str] | None = None,
) -> Envelope[PriorityLaneEligibility]:
    eligibility = build_priority_lane_eligibility(
        airport_code,
        traveler_flags=traveler_flags,
    )
    return envelope_from_model(eligibility, eligibility)
