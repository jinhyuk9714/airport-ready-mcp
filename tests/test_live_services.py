from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import (
    FlightSnapshot,
    OperationalSignal,
    ParkingLotSnapshot,
)
from departure_ready.services.flight import build_flight_envelope
from departure_ready.services.parking import build_parking_envelope


@dataclass
class _FakeParkingConnector:
    airport_code: str
    lots: list[ParkingLotSnapshot]

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    async def get_parking_status(self, airport_code: str | None = None) -> list[ParkingLotSnapshot]:
        self.calls.append(airport_code or self.airport_code)
        return self.lots


@dataclass
class _FakeFlightConnector:
    live_flights: list[FlightSnapshot]
    forecast_signals: list[OperationalSignal]
    should_fail: bool = False

    def __post_init__(self) -> None:
        self.today_calls: list[tuple[str, str | None]] = []
        self.forecast_calls: list[int] = []

    async def get_today_flights(self, flight_no: str | None = None) -> list[FlightSnapshot]:
        self.today_calls.append(("ICN", flight_no))
        if self.should_fail:
            raise RuntimeError("live source unavailable")
        return self.live_flights

    async def get_flight_status(
        self,
        airport_code: str,
        flight_no: str | None = None,
    ) -> list[FlightSnapshot]:
        self.today_calls.append((airport_code, flight_no))
        if self.should_fail:
            raise RuntimeError("live source unavailable")
        return self.live_flights

    async def get_passenger_forecast(self, selectdate: int = 0) -> list[OperationalSignal]:
        self.forecast_calls.append(selectdate)
        if self.should_fail:
            raise RuntimeError("forecast source unavailable")
        return self.forecast_signals


def _parking_lot(
    airport_code: str,
    lot_name: str,
    *,
    terminal: str | None = None,
    available_spaces: int | None = None,
    occupancy_pct: float | None = None,
    freshness: Freshness = Freshness.LIVE,
) -> ParkingLotSnapshot:
    return ParkingLotSnapshot(
        airport_code=airport_code,
        lot_name=lot_name,
        terminal=terminal,
        available_spaces=available_spaces,
        occupancy_pct=occupancy_pct,
        freshness=freshness,
        updated_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} lot",
    )


def _flight_snapshot(
    airport_code: str,
    flight_no: str,
    *,
    terminal: str | None = None,
    freshness: Freshness = Freshness.LIVE,
) -> FlightSnapshot:
    return FlightSnapshot(
        airport_code=airport_code,
        flight_no=flight_no,
        airline="Korean Air",
        terminal=terminal,
        gate="12",
        checkin_counter="A1",
        scheduled_at=datetime(2026, 3, 24, 11, 0, tzinfo=UTC),
        changed_at=datetime(2026, 3, 24, 11, 30, tzinfo=UTC),
        status_label="ON TIME",
        signal_kind="live",
        freshness=freshness,
        updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} flight",
    )


def _forecast_signal(airport_code: str, label: str) -> OperationalSignal:
    return OperationalSignal(
        airport_code=airport_code,
        signal_type="crowd_forecast",
        headline=label,
        detail="forecast detail",
        freshness=Freshness.FORECAST,
        updated_at=datetime(2026, 3, 24, 9, 50, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_forecast",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} forecast",
    )


def test_parking_service_uses_icn_source_and_keeps_known_lots():
    connector = _FakeParkingConnector(
        airport_code="ICN",
        lots=[
            _parking_lot(
                "ICN",
                "T1 short-term",
                terminal="T1",
                available_spaces=12,
                occupancy_pct=94.0,
            ),
            _parking_lot(
                "ICN",
                "T2 long-term",
                terminal="T2",
                available_spaces=120,
                occupancy_pct=30.0,
            ),
        ],
    )

    envelope = build_parking_envelope(
        "ICN",
        terminal="제1여객터미널",
        iiac_connector=connector,
    )

    assert connector.calls == ["ICN"]
    assert envelope.data.airport_code == "ICN"
    assert envelope.data.terminal == "T1"
    assert len(envelope.data.lots) == 1
    assert envelope.data.lots[0].lot_name == "T1 short-term"
    assert "Best official lot" in envelope.data.recommendation
    assert envelope.meta.freshness == Freshness.LIVE


def test_parking_service_uses_kac_source_for_non_icn():
    connector = _FakeParkingConnector(
        airport_code="GMP",
        lots=[_parking_lot("GMP", "Domestic", available_spaces=9, occupancy_pct=91.0)],
    )

    envelope = build_parking_envelope("GMP", kac_connector=connector)

    assert connector.calls == ["GMP"]
    assert envelope.data.airport_code == "GMP"
    assert envelope.data.lots[0].lot_name == "Domestic"
    assert envelope.meta.freshness == Freshness.LIVE
    assert envelope.meta.source[0].name == "fake"


def test_parking_service_reports_unsupported_airport_explicitly():
    envelope = build_parking_envelope("XYZ")

    assert envelope.ok is False
    assert envelope.data.code == "unsupported_coverage"
    assert "XYZ" in envelope.meta.coverage_note
    assert "parking" in envelope.meta.coverage_note


def test_flight_service_uses_icn_live_and_forecast_paths():
    connector = _FakeFlightConnector(
        live_flights=[_flight_snapshot("ICN", "KE123", terminal="T1")],
        forecast_signals=[_forecast_signal("ICN", "Morning forecast")],
    )

    envelope = build_flight_envelope(
        "ICN",
        flight_no="KE123",
        iiac_connector=connector,
    )

    assert connector.today_calls == [("ICN", "KE123")]
    assert connector.forecast_calls == [0]
    assert envelope.data.status == "mixed"
    assert envelope.data.selected_flight.flight_no == "KE123"
    assert len(envelope.data.live_flights) == 1
    assert len(envelope.data.forecast_signals) == 1
    assert envelope.meta.freshness == Freshness.FORECAST


def test_flight_service_uses_kac_for_non_icn_and_returns_live_only():
    connector = _FakeFlightConnector(
        live_flights=[_flight_snapshot("GMP", "OZ100")],
        forecast_signals=[],
    )

    envelope = build_flight_envelope("GMP", kac_connector=connector)

    assert connector.today_calls == [("GMP", None)]
    assert connector.forecast_calls == []
    assert envelope.data.status == "live"
    assert envelope.data.selected_flight.flight_no == "OZ100"
    assert envelope.meta.freshness == Freshness.LIVE


def test_flight_service_returns_bounded_unavailable_on_connector_failure():
    connector = _FakeFlightConnector(
        live_flights=[],
        forecast_signals=[],
        should_fail=True,
    )

    envelope = build_flight_envelope("ICN", iiac_connector=connector)

    assert envelope.ok is False
    assert envelope.data.code == "live_source_unavailable"
    assert "live source unavailable" in envelope.data.message
    assert envelope.meta.freshness == Freshness.STATIC
