from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.iiac_flight import IiacFlightConnector
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FlightSnapshot
from departure_ready.services.flight import build_flight_envelope


@dataclass
class _FakeIiacFlightConnector:
    weekly_flights: list[FlightSnapshot]

    def __post_init__(self) -> None:
        self.today_calls: list[str | None] = []
        self.weekly_calls: list[tuple[date | None, str | None]] = []
        self.forecast_calls: list[int] = []

    async def get_today_flights(self, flight_no: str | None = None) -> list[FlightSnapshot]:
        self.today_calls.append(flight_no)
        return []

    async def get_weekly_flights(
        self,
        travel_date: date | None = None,
        flight_no: str | None = None,
    ) -> list[FlightSnapshot]:
        self.weekly_calls.append((travel_date, flight_no))
        return self.weekly_flights

    async def get_passenger_forecast(self, selectdate: int = 0):
        self.forecast_calls.append(selectdate)
        return []


def _weekly_flight(
    flight_no: str = "KE123",
    *,
    freshness: Freshness = Freshness.DAILY,
) -> FlightSnapshot:
    return FlightSnapshot(
        airport_code="ICN",
        flight_no=flight_no,
        airline="Korean Air",
        terminal="T1",
        gate=None,
        checkin_counter=None,
        scheduled_at=datetime(2026, 3, 25, 11, 0, tzinfo=UTC),
        changed_at=None,
        status_label="SCHEDULED",
        signal_kind="daily",
        freshness=freshness,
        updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
        source=[
            SourceRef(
                name="iiac_flight_weekly",
                kind=SourceKind.OFFICIAL_API,
                url="https://www.data.go.kr/data/15095074/openapi.do",
            )
        ],
        coverage_note="ICN weekly passenger flight schedule",
    )


def test_future_icn_flight_uses_weekly_source_and_daily_freshness():
    future_date = date.today() + timedelta(days=3)
    connector = _FakeIiacFlightConnector([_weekly_flight()])

    envelope = build_flight_envelope(
        "ICN",
        flight_no="KE123",
        travel_date=future_date,
        iiac_connector=connector,
    )

    assert envelope.ok is True
    assert connector.today_calls == []
    assert connector.weekly_calls == [(future_date, "KE123")]
    assert connector.forecast_calls == []
    assert envelope.data.status == "daily"
    assert envelope.meta.freshness == Freshness.DAILY
    assert envelope.data.selected_flight is not None
    assert envelope.data.selected_flight.signal_kind == "daily"
    assert envelope.data.selected_flight.gate is None
    assert envelope.data.selected_flight.checkin_counter is None


def test_future_icn_flight_returns_bounded_unavailable_when_weekly_source_is_empty():
    future_date = date.today() + timedelta(days=4)
    connector = _FakeIiacFlightConnector([])

    envelope = build_flight_envelope(
        "ICN",
        travel_date=future_date,
        iiac_connector=connector,
    )

    assert envelope.ok is True
    assert connector.weekly_calls == [(future_date, None)]
    assert envelope.data.status == "unavailable"
    assert envelope.data.selected_flight is None
    assert "unavailable" in envelope.data.summary.lower()


def test_future_icn_flight_outside_weekly_horizon_does_not_guess():
    future_date = date.today() + timedelta(days=8)
    connector = _FakeIiacFlightConnector([])

    envelope = build_flight_envelope(
        "ICN",
        travel_date=future_date,
        iiac_connector=connector,
    )

    assert envelope.ok is True
    assert connector.today_calls == []
    assert connector.weekly_calls == []
    assert envelope.data.status == "unavailable"
    assert "weekly" in envelope.data.summary.lower()


def test_future_non_icn_flight_returns_unsupported_coverage():
    future_date = date.today() + timedelta(days=2)

    envelope = build_flight_envelope("GMP", travel_date=future_date)

    assert envelope.ok is False
    assert envelope.data.code == "unsupported_coverage"
    assert "ICN" in envelope.data.message
    assert "flight" in envelope.meta.coverage_note.lower()


def test_weekly_parser_keeps_live_only_fields_empty_when_source_lacks_them():
    connector = IiacFlightConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "flightId": "KE123",
                            "airline": "Korean Air",
                            "scheduleDateTime": "20260325110000",
                            "estimatedDateTime": "20260325112000",
                            "terminalId": "P03",
                            "remark": "SCHEDULED",
                        }
                    ]
                }
            }
        }
    }

    flights = connector.parse_weekly_payload(payload)

    assert flights[0].signal_kind == "daily"
    assert flights[0].freshness == Freshness.DAILY
    assert flights[0].gate is None
    assert flights[0].checkin_counter is None
