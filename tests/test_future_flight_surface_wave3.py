from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from departure_ready.api.app import create_app
from departure_ready.contracts import Envelope, Freshness, ResponseMeta, SourceKind, SourceRef
from departure_ready.mcp.server import tool_get_flight_status
from departure_ready.services.flight import FlightPayload


def _flight_payload() -> Envelope[FlightPayload]:
    return Envelope(
        meta=ResponseMeta(
            source=[
                SourceRef(
                    name="iiac_flight_weekly",
                    kind=SourceKind.OFFICIAL_API,
                    url="https://www.data.go.kr/data/15095074/openapi.do",
                )
            ],
            freshness=Freshness.DAILY,
            updated_at=datetime(2026, 3, 24, 14, 0, tzinfo=UTC),
            coverage_note="ICN weekly passenger flight schedule",
        ),
        data=FlightPayload(
            airport_code="ICN",
            status="daily",
            summary="ICN weekly flight schedule is available for 2026-03-25.",
        ),
    )


def test_http_flight_status_forwards_travel_date(monkeypatch):
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_build_flight_envelope(
        airport_code: str,
        flight_no: str | None = None,
        *,
        travel_date: str | None = None,
        settings=None,
    ):
        calls.append((airport_code, flight_no, travel_date))
        return _flight_payload()

    monkeypatch.setattr(
        "departure_ready.api.app.build_flight_envelope",
        fake_build_flight_envelope,
    )

    client = TestClient(create_app())
    response = client.get(
        "/v1/flight-status",
        params={
            "airport_code": "ICN",
            "flight_no": "KE123",
            "travel_date": "2026-03-25",
        },
    )

    assert response.status_code == 200
    assert calls == [("ICN", "KE123", "2026-03-25")]
    assert response.json()["data"]["status"] == "daily"


def test_mcp_flight_status_forwards_travel_date(monkeypatch):
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_build_flight_envelope(
        airport_code: str,
        flight_no: str | None = None,
        *,
        travel_date: str | None = None,
        settings=None,
    ):
        calls.append((airport_code, flight_no, travel_date))
        return _flight_payload()

    monkeypatch.setattr(
        "departure_ready.mcp.server.build_flight_envelope",
        fake_build_flight_envelope,
    )

    payload = tool_get_flight_status("ICN", "KE123", travel_date="2026-03-25")

    assert calls == [("ICN", "KE123", "2026-03-25")]
    assert payload["ok"] is True
    assert payload["data"]["status"] == "daily"
