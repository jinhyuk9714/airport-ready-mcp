from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from departure_ready.contracts import Envelope, Freshness, ResponseMeta, SourceKind, SourceRef
from departure_ready.domain.models import (
    FacilityMatch,
    FacilityPayload,
    FlightSnapshot,
    ParkingPayload,
)
from departure_ready.services import readiness as readiness_module
from departure_ready.services.flight import FlightPayload
from departure_ready.services.readiness import build_readiness_envelope
from departure_ready.settings import Settings


def _flight_envelope(airport_code: str) -> Envelope[FlightPayload]:
    flight = FlightSnapshot(
        airport_code=airport_code,
        flight_no="KE123",
        airline="Korean Air",
        terminal="T1",
        gate="12",
        checkin_counter="A1",
        scheduled_at=datetime(2026, 3, 24, 11, 0, tzinfo=UTC),
        changed_at=datetime(2026, 3, 24, 11, 30, tzinfo=UTC),
        status_label="ON TIME",
        signal_kind="live",
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_flight",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} flight",
    )
    payload = FlightPayload(
        airport_code=airport_code,
        status="live",
        summary=f"{airport_code} live flight status is available from the official source.",
        live_flights=[flight],
        forecast_signals=[],
        selected_flight=flight,
        missing_inputs=[],
    )
    return Envelope(
        meta=ResponseMeta(
            source=flight.source,
            freshness=Freshness.LIVE,
            updated_at=flight.updated_at,
            coverage_note=flight.coverage_note,
        ),
        data=payload,
    )


def _parking_envelope(airport_code: str) -> Envelope[ParkingPayload]:
    payload = ParkingPayload(
        airport_code=airport_code,
        recommendation=f"{airport_code} parking recommendation",
        lots=[],
        missing_inputs=[],
    )
    return Envelope(
        meta=ResponseMeta(
            source=[
                SourceRef(
                    name="fake_parking",
                    kind=SourceKind.INTERNAL,
                    url="https://example.invalid",
                )
            ],
            freshness=Freshness.STATIC,
            updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
            coverage_note=f"{airport_code} parking",
        ),
        data=payload,
    )


def _facility_match(airport_code: str, category: str, name: str) -> FacilityMatch:
    return FacilityMatch(
        airport_code=airport_code,
        terminal="T1",
        name=name,
        category=category,
        location_text=f"{category} location",
        freshness=Freshness.DAILY,
        updated_at=datetime(2026, 3, 24, 10, 10, tzinfo=UTC),
        source=[
            SourceRef(
                name=f"fake_{category}",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} {category}",
    )


@dataclass
class _FakeFacilityService:
    matches_by_category: dict[str, list[FacilityMatch]]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str | None, str | None, str | None]] = []

    async def __call__(
        self,
        settings: Settings,
        airport_code: str,
        *,
        terminal: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> Envelope[FacilityPayload]:
        self.calls.append((airport_code, terminal, category, query))
        matches = self.matches_by_category.get(category or "", [])
        payload = FacilityPayload(
            airport_code=airport_code,
            terminal=terminal,
            matches=matches,
        )
        return Envelope(
            meta=ResponseMeta(
                source=[
                    SourceRef(
                        name="fake_facilities",
                        kind=SourceKind.INTERNAL,
                        url="https://example.invalid",
                    )
                ],
                freshness=Freshness.DAILY,
                updated_at=datetime(2026, 3, 24, 10, 15, tzinfo=UTC),
                coverage_note=f"{airport_code} facilities",
            ),
            data=payload,
        )


def _stub_readiness_dependencies(monkeypatch, airport_code: str = "ICN") -> None:
    monkeypatch.setattr(
        readiness_module,
        "build_flight_envelope",
        lambda *args, **kwargs: _flight_envelope(airport_code),
    )
    monkeypatch.setattr(
        readiness_module,
        "_load_kac_operational_signals",
        lambda *args, **kwargs: ([], []),
    )
    monkeypatch.setattr(readiness_module, "_build_service_eligibility", lambda *args, **kwargs: [])


def test_readiness_uses_accessibility_intent_for_facility_hints(monkeypatch):
    _stub_readiness_dependencies(monkeypatch)
    fake_facilities = _FakeFacilityService(
        matches_by_category={
            "accessibility": [_facility_match("ICN", "accessibility", "Barrier-free elevator")],
            "medical": [_facility_match("ICN", "medical", "Pharmacy")],
            "parking": [_facility_match("ICN", "parking", "Short-term parking")],
        }
    )
    monkeypatch.setattr(readiness_module, "build_facilities_envelope", fake_facilities)

    envelope = build_readiness_envelope(
        "ICN",
        traveler_flags=["wheelchair"],
        settings=Settings(),
    )

    card = envelope.data
    assert [hint.category for hint in card.facility_hints] == [
        "accessibility",
        "medical",
        "parking",
    ]
    assert fake_facilities.calls == [
        ("ICN", None, "accessibility", None),
        ("ICN", None, "medical", None),
        ("ICN", None, "parking", None),
    ]
    assert not any(
        "facility" in action.lower() and "unavailable" in action.lower()
        for action in card.next_actions
    )


def test_readiness_limits_family_intent_facility_hints_to_three(monkeypatch):
    _stub_readiness_dependencies(monkeypatch)
    fake_facilities = _FakeFacilityService(
        matches_by_category={
            "nursery": [_facility_match("ICN", "nursery", "Nursery room")],
            "family": [_facility_match("ICN", "family", "Family lounge")],
            "medical": [_facility_match("ICN", "medical", "Clinic")],
            "restroom": [_facility_match("ICN", "restroom", "Restroom")],
        }
    )
    monkeypatch.setattr(readiness_module, "build_facilities_envelope", fake_facilities)

    envelope = build_readiness_envelope(
        "ICN",
        traveler_flags=["infant"],
        settings=Settings(),
    )

    card = envelope.data
    assert len(card.facility_hints) == 3
    assert [hint.category for hint in card.facility_hints] == [
        "nursery",
        "family",
        "medical",
    ]


def test_readiness_does_not_add_facility_hints_for_car_only(monkeypatch):
    _stub_readiness_dependencies(monkeypatch)
    fake_facilities = _FakeFacilityService(matches_by_category={})
    monkeypatch.setattr(readiness_module, "build_facilities_envelope", fake_facilities)
    monkeypatch.setattr(
        readiness_module,
        "build_parking_envelope",
        lambda *args, **kwargs: _parking_envelope("ICN"),
    )

    envelope = build_readiness_envelope(
        "ICN",
        going_by_car=True,
        settings=Settings(),
    )

    card = envelope.data
    assert card.facility_hints == []
    assert fake_facilities.calls == []


def test_readiness_marks_facilities_unavailable_when_lookup_fails(monkeypatch):
    _stub_readiness_dependencies(monkeypatch)

    async def failing_facilities(*args, **kwargs):
        raise RuntimeError("facility source down")

    monkeypatch.setattr(readiness_module, "build_facilities_envelope", failing_facilities)

    envelope = build_readiness_envelope(
        "ICN",
        traveler_flags=["disabled"],
        settings=Settings(),
    )

    card = envelope.data
    assert card.facility_hints == []
    assert any(
        "facility" in action.lower() and "unavailable" in action.lower()
        for action in card.next_actions
    )
