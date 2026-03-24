from __future__ import annotations

from datetime import UTC, datetime

from departure_ready.connectors.policy import IIAC_BAGGAGE_POLICY
from departure_ready.contracts import Envelope, Freshness
from departure_ready.domain.models import BaggageDecision
from departure_ready.services.common import envelope_from_model

LIQUID_KEYWORDS = (
    "liquid",
    "water",
    "juice",
    "bottle",
    "perfume",
    "spray",
    "gel",
    "lotion",
    "toner",
    "alcohol",
    "kimchi",
    "gochujang",
    "paste",
)

TOBACCO_KEYWORDS = ("cigarette", "cigarettes", "tobacco", "smoke", "nicotine")


def build_baggage_decision(
    item_query: str,
    trip_type: str,
    *,
    liquid_ml: float | None = None,
    battery_wh: float | None = None,
) -> BaggageDecision:
    query = item_query.strip()
    normalized = query.lower()
    now = datetime.now(UTC)

    if trip_type not in {"domestic", "international"}:
        return _decision(
            item_query=query,
            trip_type="international",
            category="manual_confirmation",
            carry_on_allowed=None,
            checked_allowed=None,
            declaration_needed=None,
            explanation=(
                "Trip type is unclear. Confirm the airline and route "
                "before relying on baggage rules."
            ),
            warnings=[
                "Trip type must be domestic or international to apply official baggage policy."
            ],
            now=now,
        )

    if trip_type == "domestic":
        if _contains(normalized, TOBACCO_KEYWORDS):
            return _decision(
                item_query=query,
                trip_type=trip_type,
                category="tobacco_item",
                carry_on_allowed=True,
                checked_allowed=True,
                declaration_needed=False,
                explanation=(
                    "Cigarettes are not a baggage-prohibited item by themselves "
                    "for domestic trips, but airline and security checks can still apply."
                ),
                warnings=[
                    "Baggage rules do not replace customs or age-related restrictions.",
                ],
                now=now,
            )

        return _decision(
            item_query=query,
            trip_type=trip_type,
            category="domestic_item",
            carry_on_allowed=True,
            checked_allowed=True,
            declaration_needed=False,
            explanation=(
                "Domestic flights do not use the international 100 ml liquid restriction. "
                "Check airline-specific exceptions for hazardous or oversized items."
            ),
            warnings=[
                "Airline restrictions can still apply to special items.",
            ],
            now=now,
        )

    if battery_wh is not None or "battery" in normalized or "보조배터리" in normalized:
        if battery_wh is None:
            return _decision(
                item_query=query,
                trip_type=trip_type,
                category="manual_confirmation",
                carry_on_allowed=True,
                checked_allowed=False,
                declaration_needed=False,
                explanation=(
                    "Spare lithium batteries must stay in carry-on baggage, but the "
                    "allowed quantity depends on the watt-hour rating."
                ),
                warnings=["Confirm the exact battery Wh with the airline."],
                manual_confirmation_required=True,
                now=now,
            )
        if battery_wh > 160:
            return _decision(
                item_query=query,
                trip_type=trip_type,
                category="battery_prohibited",
                carry_on_allowed=False,
                checked_allowed=False,
                declaration_needed=False,
                explanation="Spare lithium batteries above 160 Wh are not allowed.",
                warnings=["Airlines can deny oversized batteries."],
                now=now,
            )
        if battery_wh > 100:
            return _decision(
                item_query=query,
                trip_type=trip_type,
                category="battery_airline_approval",
                carry_on_allowed=True,
                checked_allowed=False,
                declaration_needed=False,
                explanation=(
                    "Spare lithium batteries over 100 Wh and up to 160 Wh require "
                    "airline approval and are limited to carry-on."
                ),
                warnings=["Carry-on only, up to two with airline approval."],
                manual_confirmation_required=True,
                now=now,
            )
        return _decision(
            item_query=query,
            trip_type=trip_type,
            category="battery_carry_on_only",
            carry_on_allowed=True,
            checked_allowed=False,
            declaration_needed=False,
            explanation=(
                "Spare lithium batteries up to 100 Wh are carry-on only and limited in quantity."
            ),
            warnings=["Carry-on only, usually up to five spare batteries."],
            now=now,
        )

    if _contains(normalized, TOBACCO_KEYWORDS):
        return _decision(
            item_query=query,
            trip_type=trip_type,
            category="tobacco_item",
            carry_on_allowed=True,
            checked_allowed=True,
            declaration_needed=False,
            explanation=(
                "Cigarettes are not a baggage-prohibited item on their own, "
                "but customs rules are separate."
            ),
            warnings=[
                "Confirm customs allowances separately for tobacco products.",
            ],
            now=now,
        )

    if _contains(normalized, LIQUID_KEYWORDS):
        item_note = ""
        liquid_rule = (
            "each container must be 100 ml or less and go into one transparent 1 L ziplock bag."
        )
        carry_on_allowed = False
        manual_confirmation_required = True
        if liquid_ml is not None and liquid_ml <= 100:
            carry_on_allowed = True
            manual_confirmation_required = False
        if liquid_ml is not None and liquid_ml > 100:
            liquid_rule = "the container exceeds the 100 ml carry-on limit."
        if "kimchi" in normalized or "gochujang" in normalized:
            item_note = " Kimchi and gochujang are treated as liquid or gel-type items."
        elif "alcohol" in normalized:
            item_note = " Alcohol is still subject to airline and destination limits."
        elif "perfume" in normalized:
            item_note = " Perfume is treated as a liquid item."

        return _decision(
            item_query=query,
            trip_type=trip_type,
            category="liquid_restricted",
            carry_on_allowed=carry_on_allowed,
            checked_allowed=True,
            declaration_needed=False,
            explanation=(
                "For international departures from Incheon, liquids, sprays, "
                f"and gels are restricted: {liquid_rule}"
                f"{item_note}"
            ),
            warnings=[
                (
                    "Kimchi and gochujang are treated like liquid/gel-type items "
                    "for carry-on screening."
                ),
                (
                    "Alcohol and perfume are liquid items; airline and destination "
                    "rules can add extra limits."
                ),
            ],
            manual_confirmation_required=manual_confirmation_required,
            now=now,
        )

    return _decision(
        item_query=query,
        trip_type=trip_type,
        category="manual_confirmation",
        carry_on_allowed=None,
        checked_allowed=None,
        declaration_needed=False,
        explanation=(
            "The item is not matched to a specific prohibited category in the official "
            "baggage policy. Confirm the airline if it is unusual, sharp, pressurized, "
            "or hazardous."
        ),
        warnings=[
            ("This answer only covers official baggage policy, not customs or airline exceptions."),
        ],
        now=now,
    )


def _decision(
    *,
    item_query: str,
    trip_type: str,
    category: str,
    carry_on_allowed: bool | None,
    checked_allowed: bool | None,
    declaration_needed: bool | None,
    explanation: str,
    warnings: list[str],
    now: datetime,
    manual_confirmation_required: bool = False,
) -> BaggageDecision:
    return BaggageDecision(
        item_query=item_query,
        trip_type=trip_type,  # type: ignore[arg-type]
        category=category,
        carry_on_allowed=carry_on_allowed,
        checked_allowed=checked_allowed,
        declaration_needed=declaration_needed,
        explanation=explanation,
        warnings=warnings,
        manual_confirmation_required=manual_confirmation_required,
        source=IIAC_BAGGAGE_POLICY.source(),
        freshness=Freshness.POLICY,
        updated_at=now,
        coverage_note=(
            "Official Incheon baggage policy; customs, airline, and destination rules are separate."
        ),
    )


def _contains(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def build_baggage_envelope(
    item_query: str,
    trip_type: str,
    *,
    liquid_ml: float | None = None,
    battery_wh: float | None = None,
) -> Envelope[BaggageDecision]:
    decision = build_baggage_decision(
        item_query,
        trip_type,
        liquid_ml=liquid_ml,
        battery_wh=battery_wh,
    )
    return envelope_from_model(decision, decision)
