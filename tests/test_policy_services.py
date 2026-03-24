from __future__ import annotations

from departure_ready.contracts import Freshness
from departure_ready.services.baggage import build_baggage_decision
from departure_ready.services.customs import build_customs_guidance
from departure_ready.services.self_service import (
    build_priority_lane_eligibility,
    build_self_service_options,
)


def test_baggage_rules_cover_liquids_and_pastes():
    liquids = build_baggage_decision("bottle of water", "international")
    paste = build_baggage_decision("gochujang", "international")

    assert liquids.carry_on_allowed is False
    assert liquids.manual_confirmation_required is True
    assert "100 ml" in liquids.explanation
    assert liquids.freshness == Freshness.POLICY
    assert liquids.source[0].name == "iiac_baggage_policy"

    assert paste.carry_on_allowed is False
    assert paste.manual_confirmation_required is True
    assert "kimchi" in paste.explanation.lower() or "gochujang" in paste.explanation.lower()


def test_baggage_rules_cover_alcohol_perfume_and_cigarettes():
    alcohol = build_baggage_decision("alcohol", "international")
    perfume = build_baggage_decision("perfume", "international")
    cigarettes = build_baggage_decision("cigarettes", "international")

    assert alcohol.category == "liquid_restricted"
    assert perfume.category == "liquid_restricted"
    assert cigarettes.carry_on_allowed is True
    assert cigarettes.checked_allowed is True
    assert "customs" in cigarettes.explanation.lower()


def test_customs_rules_cover_thresholds_and_allowances():
    guidance = build_customs_guidance(
        item_query="gift alcohol perfume cigarettes",
        purchase_value_usd=950,
        alcohol_liters=2.5,
        perfume_ml=120,
        cigarette_count=250,
    )

    assert guidance.declaration_required is True
    assert guidance.duty_free_threshold_usd == 800.0
    assert any("800" in item for item in guidance.allowances)
    assert any("alcohol" in item.lower() for item in guidance.warnings)
    assert any("perfume" in item.lower() for item in guidance.warnings)
    assert any("cigarette" in item.lower() for item in guidance.warnings)
    assert guidance.freshness == Freshness.POLICY


def test_customs_rules_are_bounded_when_inputs_are_partial():
    guidance = build_customs_guidance(item_query="gift")

    assert guidance.declaration_required is None
    assert guidance.purchase_value_usd is None
    assert guidance.warnings
    assert "confirm" in guidance.summary.lower()


def test_self_service_marks_kac_airports_unsupported():
    options = build_self_service_options("GMP", airline="Korean Air")

    assert options.smart_pass_supported is False
    assert options.self_checkin_supported is False
    assert options.easy_drop_supported is False
    assert any("ICN-only" in note for note in options.notes)
    assert options.source[0].name == "iiac_smartpass"


def test_self_service_marks_icn_services_supported_with_airline_notes():
    options = build_self_service_options("ICN", airline="Korean Air")

    assert options.smart_pass_supported is True
    assert options.self_checkin_supported is True
    assert options.self_bag_drop_supported is True
    assert options.easy_drop_supported is True
    assert any("self check-in" in note.lower() for note in options.notes)


def test_priority_lane_supports_icn_profiles_and_rejects_kac_airports():
    eligible = build_priority_lane_eligibility(
        "ICN",
        traveler_flags=["mobility_impaired", "pregnant"],
    )
    unsupported = build_priority_lane_eligibility("CJU", traveler_flags=["pregnant"])

    assert eligible.eligible is True
    assert any("pregnant" in item.lower() for item in eligible.evidence)
    assert eligible.freshness == Freshness.POLICY

    assert unsupported.eligible is False
    assert "ICN-only" in unsupported.reason
